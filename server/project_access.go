package server

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
	"strings"
)

type projectAccessProfile struct {
	Mode                    string          `json:"mode"`
	MultiEnd                string          `json:"multi_end"`
	ManagementScope         string          `json:"management_scope"`
	ManagementInternalScope string          `json:"management_internal_scope"`
	ClientScope             string          `json:"client_scope"`
	SharedManagement        string          `json:"shared_management"`
	Advanced                json.RawMessage `json:"advanced,omitempty"`
	Notes                   string          `json:"notes"`
}

func emptyAccessProfile() projectAccessProfile {
	return projectAccessProfile{
		Mode:                    "simple",
		MultiEnd:                "unknown",
		ManagementScope:         "unknown",
		ManagementInternalScope: "unknown",
		ClientScope:             "unknown",
		SharedManagement:        "unknown",
	}
}

func parseAccessProfile(raw json.RawMessage) projectAccessProfile {
	p := emptyAccessProfile()
	if len(raw) == 0 || string(raw) == "null" {
		return p
	}
	_ = json.Unmarshal(raw, &p)
	if p.Mode == "" {
		p.Mode = "simple"
	}
	if p.MultiEnd == "" {
		p.MultiEnd = "unknown"
	}
	if p.ManagementScope == "" {
		p.ManagementScope = "unknown"
	}
	if p.ManagementInternalScope == "" {
		p.ManagementInternalScope = "unknown"
	}
	if p.ClientScope == "" {
		p.ClientScope = "unknown"
	}
	if p.SharedManagement == "" {
		p.SharedManagement = "unknown"
	}
	return p
}

func validChoice(v string, allowed ...string) bool {
	for _, x := range allowed {
		if v == x {
			return true
		}
	}
	return false
}

func normalizeAccessProfile(in projectAccessProfile) (projectAccessProfile, error) {
	in.Mode = strings.TrimSpace(in.Mode)
	if in.Mode == "" {
		in.Mode = "simple"
	}
	in.MultiEnd = strings.TrimSpace(in.MultiEnd)
	in.ManagementScope = strings.TrimSpace(in.ManagementScope)
	in.ManagementInternalScope = strings.TrimSpace(in.ManagementInternalScope)
	in.ClientScope = strings.TrimSpace(in.ClientScope)
	in.SharedManagement = strings.TrimSpace(in.SharedManagement)
	in.Notes = strings.TrimSpace(in.Notes)
	if !validChoice(in.Mode, "simple", "advanced") {
		return in, fmt.Errorf("mode 不合法")
	}
	if in.Mode == "advanced" {
		if len(in.Advanced) == 0 || string(in.Advanced) == "null" {
			return in, fmt.Errorf("精细模式需要填写 advanced 规则")
		}
		var obj map[string]any
		if err := json.Unmarshal(in.Advanced, &obj); err != nil {
			return in, fmt.Errorf("advanced 必须是合法 JSON 对象")
		}
		if len(obj) == 0 {
			return in, fmt.Errorf("advanced 不能为空对象")
		}
	}
	if !validChoice(in.MultiEnd, "yes", "no", "unknown") {
		return in, fmt.Errorf("multi_end 不合法")
	}
	if !validChoice(in.ManagementScope, "all", "department", "assigned", "self", "unknown") {
		return in, fmt.Errorf("management_scope 不合法")
	}
	if !validChoice(in.ManagementInternalScope, "all", "department", "self", "unknown") {
		return in, fmt.Errorf("management_internal_scope 不合法")
	}
	if !validChoice(in.ClientScope, "self", "public", "unknown") {
		return in, fmt.Errorf("client_scope 不合法")
	}
	if !validChoice(in.SharedManagement, "yes", "no", "unknown") {
		return in, fmt.Errorf("shared_management 不合法")
	}
	if len([]rune(in.Notes)) > 4000 {
		return in, fmt.Errorf("notes 不能超过 4000 字")
	}
	return in, nil
}

func accessProfileBlock(raw json.RawMessage) string {
	p := parseAccessProfile(raw)
	if p.Mode == "advanced" && len(p.Advanced) > 0 && string(p.Advanced) != "null" {
		var pretty bytes.Buffer
		if err := json.Indent(&pretty, p.Advanced, "", "  "); err != nil {
			pretty.Write(p.Advanced)
		}
		return "【项目访问模型（精细模式，业务参考，不替代源码证据）】\n" + pretty.String() +
			"\n\n判断规则：优先按上述资源/角色/数据范围规则判断；规则未覆盖的接口或角色写 needs_more，不要猜业务允许。\n"
	}
	if p.MultiEnd == "unknown" && p.ManagementScope == "unknown" && p.ManagementInternalScope == "unknown" && p.ClientScope == "unknown" && p.SharedManagement == "unknown" && p.Notes == "" {
		return ""
	}
	label := func(v, yes, no string) string {
		switch v {
		case "yes":
			return yes
		case "no":
			return no
		default:
			return "不确定"
		}
	}
	scopeLabel := func(v string) string {
		switch v {
		case "all":
			return "允许访问全部数据"
		case "department":
			return "只能访问所属部门/科室数据"
		case "assigned":
			return "只能访问分配给当前主体的数据"
		case "self":
			return "只能访问本人数据"
		case "public":
			return "公开/共享数据"
		default:
			return "不确定"
		}
	}
	var b strings.Builder
	b.WriteString("【项目访问模型（业务参考，不替代源码证据）】\n")
	b.WriteString("- 多端系统：" + label(p.MultiEnd, "是", "否") + "\n")
	b.WriteString("- 管理端业务数据范围（患者/客户/订单等）：" + scopeLabel(p.ManagementScope) + "\n")
	b.WriteString("- 管理端内部资料范围（医生/员工/管理员等）：" + scopeLabel(p.ManagementInternalScope) + "\n")
	b.WriteString("- 客户端数据范围：" + scopeLabel(p.ClientScope) + "\n")
	b.WriteString("- 客户端可访问的管理端接口：" + label(p.SharedManagement, "有", "没有") + "\n")
	if p.Notes != "" {
		b.WriteString("- 业务补充：" + p.Notes + "\n")
	}
	b.WriteString("\n判断规则：\n")
	b.WriteString("- 管理端业务数据 scope=all：角色级校验存在且无对象级限制时，不因缺少 subject/resource 绑定而直接判定越权；仍必须检查代码证据。\n")
	b.WriteString("- 管理端业务数据 scope=department/assigned/self：必须找到对应的部门、归属或分配条件；没有则按越权处理。\n")
	b.WriteString("- 管理端内部资料 scope=all：允许管理端角色查看全部医生/员工资料；scope=self 时必须绑定当前主体；scope=department 时必须绑定部门/科室条件。\n")
	b.WriteString("- 客户端 scope=self：必须有 principal 与资源的归属绑定；没有则按越权处理。\n")
	b.WriteString("- scope=unknown 或接口端别无法判断：写 needs_more，不要猜业务允许。\n")
	b.WriteString("- 若项目声明存在客户端可访问的管理端接口，按共享接口单独判断；不能把整个管理端范围改成公开。\n")
	return b.String()
}

func (s *Server) getProjectAccessProfile(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || id <= 0 {
		writeErr(w, 400, "项目 ID 不合法")
		return
	}
	p, err := s.m.pg.CodeProjects().Get(id)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	if p == nil {
		writeErr(w, 404, "项目不存在")
		return
	}
	writeJSON(w, 200, map[string]any{"access_profile": parseAccessProfile(p.AccessProfile)})
}

func (s *Server) putProjectAccessProfile(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil || id <= 0 {
		writeErr(w, 400, "项目 ID 不合法")
		return
	}
	p, err := s.m.pg.CodeProjects().Get(id)
	if err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	if p == nil {
		writeErr(w, 404, "项目不存在")
		return
	}
	var in projectAccessProfile
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		writeErr(w, 400, "请求格式不正确")
		return
	}
	in, err = normalizeAccessProfile(in)
	if err != nil {
		writeErr(w, 400, err.Error())
		return
	}
	raw, _ := json.Marshal(in)
	if err := s.m.pg.CodeProjects().SetAccessProfile(id, raw); err != nil {
		writeErr(w, 500, err.Error())
		return
	}
	writeJSON(w, 200, map[string]any{"access_profile": in})
}
