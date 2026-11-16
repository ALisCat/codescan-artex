package server

// 二开：审计矩阵的路由。
//
// 矩阵不接管 planner：导入时把格子预置成 intent（kind=intent, state=open），
// 现有 planner/worker 流程原样消费 frontier。planner 的提示词已经规定
// "已有 open/running 覆盖的方向不再生成"，因此不会重复联想。

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"github.com/Autumn-27/artex/db"
)

// 矩阵类型的中文名（用于生成任务方向）。
var cellVulnCN = map[string]string{
	"file-upload": "文件上传", "path-traversal": "路径穿越", "sql-injection": "SQL 注入",
	"command-exec": "命令/表达式注入", "ssrf": "SSRF", "deserialization": "不安全反序列化",
	"xss": "XSS", "authz": "越权",
}

// importCellsBody 是 POST /api/codeaudit/tasks/{id}/import 的请求体。
type importCellsBody struct {
	Tasks []db.CellInput `json:"tasks"`
	// Seed=true 时导入后立即把待办格子转成意图（默认 true）。
	Seed *bool `json:"seed,omitempty"`
}

// caImportCells 导入矩阵并（可选）生成意图。
func (s *Server) caImportCells(w http.ResponseWriter, r *http.Request) {
	if currentUser(r) == nil {
		writeErr(w, 401, "未授权")
		return
	}
	t, ok := s.m.Task(r.PathValue("id"))
	if !ok {
		writeErr(w, 404, "task not found")
		return
	}
	var body importCellsBody
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, 400, "bad json: "+err.Error())
		return
	}
	if len(body.Tasks) == 0 {
		writeErr(w, 400, "tasks 为空")
		return
	}
	taskID, _ := strconv.ParseInt(t.ID, 10, 64)
	n, err := s.m.PG().Cells().Import(taskID, body.Tasks)
	if err != nil {
		writeErr(w, 500, "导入失败: "+err.Error())
		return
	}
	seeded := 0
	if body.Seed == nil || *body.Seed {
		seeded, err = s.seedCellIntents(t, 0)
		if err != nil {
			writeErr(w, 500, fmt.Sprintf("导入 %d 条成功，但生成意图失败: %v", n, err))
			return
		}
	}
	writeJSON(w, 200, map[string]any{
		"imported": n,
		"seeded":   seeded,
		"task_id":  taskID,
	})
}

// 人工发起审计时补齐判定标准（矩阵里 N/A/低置信格子通常没有 checklist）。
var cellChecklistCN = map[string][]string{
	"file-upload":     {"扩展名 / Content-Type 白名单", "文件名净化（../、绝对路径、空字节）", "存储目录是否可执行 / 是否可覆盖已有文件", "大小限制"},
	"path-traversal":  {"是否拼接了用户可控路径/文件名", "有无 ../ 过滤或规范化校验（getCanonicalPath）", "是否限制在固定根目录下"},
	"sql-injection":   {"是否使用 #{} 占位符或 ? 参数化", "${} 或字符串拼接的位置", "order by / like / in 等特殊位置的过滤"},
	"command-exec":    {"参数是否进入执行/求值 API", "有无白名单或类型约束", "是否可通过表达式/编码绕过"},
	"ssrf":            {"URL 是否完全可控", "有无协议 / 域名 / IP 白名单", "是否允许内网地址与重定向"},
	"deserialization": {"是否对不可信数据做原生反序列化", "有无类白名单 / SafeMode", "依赖是否存在可利用 gadget"},
	"xss":             {"输出是否转义", "是否写入可渲染位置", "前端渲染方式"},
	"authz":           {"是否有 principal 介入数据访问", "归属谓词写在哪（SQL / Java / 注解）", "是否把判定委托给外部服务"},
}

// manualAuditBody 是 POST /api/codeaudit/tasks/{id}/cells/audit 的请求体。
type manualAuditBody struct {
	CellKey    string `json:"cell_key"`
	Suggestion string `json:"suggestion"`
}

// caManualAudit 人工对某个格子发起一次 worker 审计。
// 即使矩阵判定为 not_applicable / hold / unverified，也允许人工强制派单；
// 审计建议会随意图一起下发给 worker。
func (s *Server) caManualAudit(w http.ResponseWriter, r *http.Request) {
	if currentUser(r) == nil {
		writeErr(w, 401, "未授权")
		return
	}
	t, ok := s.m.Task(r.PathValue("id"))
	if !ok {
		writeErr(w, 404, "task not found")
		return
	}
	var body manualAuditBody
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, 400, "bad json: "+err.Error())
		return
	}
	if strings.TrimSpace(body.CellKey) == "" {
		writeErr(w, 400, "cell_key 不能为空")
		return
	}
	suggestion := strings.TrimSpace(body.Suggestion)
	if len([]rune(suggestion)) > 2000 {
		writeErr(w, 400, "审计建议不能超过 2000 字")
		return
	}
	life := t.lifecycleSnapshot()
	if isTerminalStatus(life.Status) {
		writeErr(w, 409, "任务已结束，请重跑任务或新建任务后再发起审计")
		return
	}
	taskID, err := parseTaskID(t.ID)
	if err != nil {
		writeErr(w, 400, "task id 无效")
		return
	}
	c, err := s.m.PG().Cells().Get(taskID, body.CellKey)
	if err != nil {
		writeErr(w, 500, "读取格子失败: "+err.Error())
		return
	}
	if c == nil {
		writeErr(w, 404, "格子不存在")
		return
	}
	if c.Status == "dispatched" {
		writeErr(w, 409, "该格子已在审计队列中（intent 已存在）")
		return
	}
	var checklist []string
	if len(c.Checklist) > 0 {
		_ = json.Unmarshal(c.Checklist, &checklist)
	}
	if len(checklist) == 0 {
		checklist = cellChecklistCN[c.VulnClass]
	}
	if checklist == nil {
		checklist = []string{}
	}
	var hints any
	if len(c.Hints) > 0 {
		_ = json.Unmarshal(c.Hints, &hints)
	}
	if hints == nil {
		hints = map[string]any{}
	}
	cn := cellVulnCN[c.VulnClass]
	if cn == "" {
		cn = c.VulnClass
	}
	cases := []map[string]any{{
		"cell_key":  c.CellKey,
		"vulnclass": c.VulnClass,
		"checklist": checklist,
		"hints":     hints,
	}}
	payload := map[string]any{
		"summary":    fmt.Sprintf("人工发起：审计 %s %s 的「%s」风险", c.Method, c.EndpointURL, cn),
		"cell_keys":  []string{c.CellKey},
		"cases":      cases,
		"manual":     true,
		"suggestion": suggestion,
		"hints_note": "人工发起：矩阵原判定可能是不适用 / 有守卫 / 未验证；请优先按人工建议审计这一格，" +
			"但仍以源码证据为准，结论只能是 confirmed / clean / needs_more。",
		"output_contract": map[string]any{
			"verdicts":            []string{"confirmed", "clean", "needs_more"},
			"per_cell":            "cases 里每个 cell_key 都要单独 submit_cell_verdict",
			"confirmed_requires":  "文件:行号 + 代码片段 + 触发条件；同一处代码只报一条 finding",
			"clean_requires":      "正向证据：哪一行做了什么校验",
			"needs_more_requires": "说明缺什么证据",
		},
	}
	es := s.m.PG().Exploration(t.ExpID)
	id, err := es.AddIntent(payload, 10, nil, "manual")
	if err != nil {
		writeErr(w, 500, "创建意图失败: "+err.Error())
		return
	}
	if originID, _ := t.Store.OriginFactID(); originID > 0 {
		_ = t.Store.Link(originID, db.RelDerivedFrom, id)
	}
	direction := fmt.Sprintf("人工指定：审计 %s %s 的「%s」风险", c.Method, c.EndpointURL, cn)
	reason := "人工发起审计"
	if strings.TrimSpace(c.Reason) != "" {
		reason += "（原判定：" + c.Reason + "）"
	}
	n, err := s.m.PG().Cells().MarkManual(taskID, c.CellKey, id, direction, reason)
	if err != nil {
		writeErr(w, 500, "绑定格子失败: "+err.Error())
		return
	}
	if n == 0 {
		writeErr(w, 409, "格子状态已变化（可能刚被自动派发），请刷新后重试")
		return
	}
	t.Notify()
	writeJSON(w, 200, map[string]any{
		"ok":          true,
		"intent_id":   id,
		"task_status": life.Status,
		"paused":      life.Paused,
		"queued":      life.Queued,
	})
}

// caSeedCells 手动把剩余待办格子转成意图（分批调用，默认 50 条）。
func (s *Server) caSeedCells(w http.ResponseWriter, r *http.Request) {
	if currentUser(r) == nil {
		writeErr(w, 401, "未授权")
		return
	}
	t, ok := s.m.Task(r.PathValue("id"))
	if !ok {
		writeErr(w, 404, "task not found")
		return
	}
	limit := 50
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			limit = n
		}
	}
	n, err := s.seedCellIntents(t, limit)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"seeded": n})
}

// caListCells 列出格子。
func (s *Server) caListCells(w http.ResponseWriter, r *http.Request) {
	if currentUser(r) == nil {
		writeErr(w, 401, "未授权")
		return
	}
	t, ok := s.m.Task(r.PathValue("id"))
	if !ok {
		writeErr(w, 404, "task not found")
		return
	}
	taskID, _ := strconv.ParseInt(t.ID, 10, 64)
	cells, err := s.m.PG().Cells().List(taskID, r.URL.Query().Get("status"))
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"cells": cells, "count": len(cells)})
}

// caCellStats 返回覆盖率与分布。
func (s *Server) caCellStats(w http.ResponseWriter, r *http.Request) {
	if currentUser(r) == nil {
		writeErr(w, 401, "未授权")
		return
	}
	t, ok := s.m.Task(r.PathValue("id"))
	if !ok {
		writeErr(w, 404, "task not found")
		return
	}
	taskID, _ := strconv.ParseInt(t.ID, 10, 64)
	st, err := s.m.PG().Cells().Stats(taskID)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 200, st)
}

// caSubmitVerdict 回写某个格子的结论（HTTP 入口；worker 侧走同名工具）。
func (s *Server) caSubmitVerdict(w http.ResponseWriter, r *http.Request) {
	if currentUser(r) == nil {
		writeErr(w, 401, "未授权")
		return
	}
	t, ok := s.m.Task(r.PathValue("id"))
	if !ok {
		writeErr(w, 404, "task not found")
		return
	}
	var body struct {
		CellKey  string          `json:"cell_key"`
		Verdict  string          `json:"verdict"`
		Reason   string          `json:"reason"`
		Evidence json.RawMessage `json:"evidence"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, 400, "bad json: "+err.Error())
		return
	}
	taskID, _ := strconv.ParseInt(t.ID, 10, 64)
	if err := s.m.PG().Cells().SubmitVerdict(taskID, body.CellKey, body.Verdict, body.Reason, body.Evidence); err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"ok": true})
}

// seedCellIntents 把待办格子转成探索意图。
//
// v0.4：同一接口的多个类型合并成【一个】意图（矩阵仍是每格一行，账本不受影响）。
// 目的：同一处代码只由同一个 worker 判定一次，避免 command-exec 与
// deserialization 对同一个 new Yaml() 各报一条 finding。
func (s *Server) seedCellIntents(t *Task, limit int) (int, error) {
	maxGroups := limit
	if maxGroups <= 0 {
		maxGroups = 10000
	}
	taskID, err := parseTaskID(t.ID)
	if err != nil {
		return 0, err
	}
	// 演示/评测阶段可关掉合并派发（一接口多格拆成多个意图），便于单独观察每格成本。
	maxPer := 4
	if v, ok, _ := s.m.PG().GetSetting("matrix_merge_dispatch"); ok && v == "false" {
		maxPer = 1
	}
	groups, err := s.m.PG().Cells().PendingGroups(taskID, maxGroups, maxPer)
	if err != nil {
		return 0, err
	}
	if len(groups) == 0 {
		return 0, nil
	}
	es := s.m.PG().Exploration(t.ExpID)
	// 矩阵意图必须挂到任务起点（origin fact），否则图上是一堆孤立节点、看不出衍生关系。
	originID, _ := t.Store.OriginFactID()
	seeded := 0
	for _, g := range groups {
		cellKeys := make([]string, 0, len(g.Cells))
		names := make([]string, 0, len(g.Cells))
		cases := make([]map[string]any, 0, len(g.Cells))
		prio := 0
		for _, c := range g.Cells {
			cellKeys = append(cellKeys, c.CellKey)
			names = append(names, cellVulnCN[c.VulnClass])
			var checklist []string
			_ = json.Unmarshal(c.Checklist, &checklist)
			var hints map[string]any
			_ = json.Unmarshal(c.Hints, &hints)
			cases = append(cases, map[string]any{
				"cell_key": c.CellKey, "vulnclass": c.VulnClass,
				"checklist": checklist, "hints": hints,
			})
			if c.Priority > prio {
				prio = c.Priority
			}
		}
		summary := fmt.Sprintf("审计 %s %s 的「%s」风险（%d 个判定项）",
			g.Method, g.EndpointURL, strings.Join(names, "、"), len(cases))
		note := ""
		for _, c := range g.Cells {
			if strings.TrimSpace(c.HintsNote) != "" {
				note = c.HintsNote
				break
			}
		}
		if note == "" {
			note = "线索由静态分析自动生成，可能不准确或不完整；请独立核实。"
		}
		payload := map[string]any{
			"summary":    summary,
			"cell_keys":  cellKeys,
			"cases":      cases,
			"hints_note": note,
			"output_contract": map[string]any{
				"verdicts":            []string{"confirmed", "clean", "needs_more"},
				"per_cell":            "cases 里每个 cell_key 都要单独 submit_cell_verdict",
				"confirmed_requires":  "文件:行号 + 代码片段 + 触发条件；同一处代码只报一条 finding",
				"clean_requires":      "正向证据：哪一行做了什么校验",
				"needs_more_requires": "说明缺什么证据",
			},
		}
		id, err := es.AddIntent(payload, matrixPriority(prio), nil, "matrix")
		if err != nil {
			return seeded, fmt.Errorf("生成意图失败 %s: %w", g.EndpointURL, err)
		}
		if originID > 0 {
			_ = t.Store.Link(originID, db.RelDerivedFrom, id)
		}
		for _, c := range g.Cells {
			if err := s.m.PG().Cells().MarkDispatched(c.ID, id); err != nil {
				return seeded, err
			}
		}
		seeded++
	}
	return seeded, nil
}

// matrixPriority 把矩阵的 0-40 分压到意图的 1-10。
func matrixPriority(p int) int {
	switch {
	case p >= 30:
		return 10
	case p >= 24:
		return 8
	case p >= 16:
		return 6
	case p >= 10:
		return 4
	default:
		return 3
	}
}

// matrixGuardForTask 限制矩阵任务的 planner 补派额度：
//   - 非矩阵任务（没有 ca_cells）→ 不限制；
//   - 矩阵任务 → planner 来源的意图数不得超过 matrix_planner_extra_limit（默认 10）。
//
// 目的：矩阵本身已枚举方向，planner 只应补"矩阵没覆盖的缺口"，不应再派
// "汇总/盘点/落盘"这类元任务。
func (s *Server) matrixGuardForTask(t *Task) (bool, string) {
	if s.m == nil || s.m.PG() == nil || t == nil {
		return true, ""
	}
	taskID, err := parseTaskID(t.ID)
	if err != nil {
		return true, ""
	}
	n, err := s.m.PG().Cells().Count(taskID)
	if err != nil || n == 0 {
		return true, "" // 非矩阵任务
	}
	limit := 10
	if v, ok, _ := s.m.PG().GetSetting("matrix_planner_extra_limit"); ok {
		if k, err := strconv.Atoi(v); err == nil && k >= 0 {
			limit = k
		}
	}
	used, err := t.Store.CountIntentsByOrigin("planner")
	if err != nil {
		return true, ""
	}
	if used >= limit {
		return false, "矩阵任务的本轮补派额度已用完（" + strconv.Itoa(used) + "/" + strconv.Itoa(limit) +
			"）。矩阵已经枚举了方向，请优先把已有格子跑完；确需补派时提高 settings.matrix_planner_extra_limit。" +
			"另：不要生成汇总/盘点/落盘/对照表这类元任务。"
	}
	return true, ""
}
