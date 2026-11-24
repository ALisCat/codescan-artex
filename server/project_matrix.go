package server

// 二开：项目审计在全量源码就绪后，自动跑矩阵分析并导入 ca_cells。
//
// 矩阵实现仍然是 codeaudit/matrix 下的 Python 工具链；这里只负责按固定顺序
// 调用它，然后把生成的 import.json 交给同一套 DB/seed 路径。不要让项目审计
// 绕过矩阵直接启动标准 planner——否则同一类任务会出现两种完全不同的执行路径。

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/Autumn-27/artex/db"
)

const matrixAnalyzerList = "authz,authn,sql-injection,command-exec,ssrf,file-upload,path-traversal,deserialization,xss,business_logic,xxe,csrf,open_redirect,ssti,ldap_injection,mass_assignment,race_condition,secrets,crypto,dependency,sensitive_data"

func (s *Server) codeauditDir() (string, error) {
	if v := strings.TrimSpace(os.Getenv("ARTEX_CODEAUDIT_DIR")); v != "" {
		if fileExists(filepath.Join(v, "matrix", "graph", "build.py")) {
			return v, nil
		}
	}
	candidates := []string{
		"src/codeaudit",
		"codeaudit",
	}
	if exe, err := os.Executable(); err == nil {
		dir := filepath.Dir(exe)
		candidates = append(candidates,
			filepath.Join(dir, "src", "codeaudit"),
			filepath.Join(dir, "codeaudit"),
		)
	}
	if s != nil && s.m != nil && s.m.dir != "" {
		candidates = append(candidates, filepath.Join(s.m.dir, "..", "src", "codeaudit"))
	}
	for _, c := range candidates {
		abs, err := filepath.Abs(c)
		if err == nil && fileExists(filepath.Join(abs, "matrix", "graph", "build.py")) {
			return abs, nil
		}
	}
	return "", fmt.Errorf("找不到矩阵分析器目录（matrix/graph/build.py）；可设置 ARTEX_CODEAUDIT_DIR")
}

func fileExists(path string) bool {
	fi, err := os.Stat(path)
	return err == nil && !fi.IsDir()
}

func (s *Server) matrixPython() string {
	if p := strings.TrimSpace(s.pythonInterpreter()); p != "" {
		if filepath.IsAbs(p) {
			if fileExists(p) {
				return p
			}
		} else if p, err := exec.LookPath(p); err == nil {
			return p
		}
	}
	if p, err := exec.LookPath("python3"); err == nil {
		return p
	}
	if p, err := exec.LookPath("python"); err == nil {
		return p
	}
	return ""
}

func (s *Server) runMatrixCommand(ctx context.Context, dir, python string, args ...string) error {
	start := time.Now()
	cmd := exec.CommandContext(ctx, python, args...)
	cmd.Dir = dir
	env := os.Environ()
	// GraphBuilder imports sibling packages by module path; make the module root
	// explicit so the command also works when the server cwd is /opt/codescan.
	env = append(env, "PYTHONPATH="+dir)
	cmd.Env = env
	out, err := cmd.CombinedOutput()
	elapsed := time.Since(start).Round(time.Millisecond)
	if err != nil {
		msg := strings.TrimSpace(string(out))
		if len(msg) > 3000 {
			msg = msg[len(msg)-3000:]
		}
		return fmt.Errorf("%s 失败（%s）: %w；输出: %s", args[0], elapsed, err, msg)
	}
	log.Printf("[matrix] %s 完成（%s）%s", args[0], elapsed, strings.TrimSpace(string(out)))
	return nil
}

// buildMatrixImport runs the Python matrix pipeline and returns the platform
// import body. It does not touch tasks or ca_cells; callers decide whether to
// import (task audit) or only inspect delta cells (incremental preparation).
func (s *Server) buildMatrixImport(ctx context.Context, sourceDir, outDir string) (importCellsBody, error) {
	var body importCellsBody
	codeauditDir, err := s.codeauditDir()
	if err != nil {
		return body, err
	}
	python := s.matrixPython()
	if python == "" {
		return body, fmt.Errorf("找不到 python3，无法运行矩阵分析器")
	}
	if fi, err := os.Stat(sourceDir); err != nil || !fi.IsDir() {
		return body, fmt.Errorf("源码目录不存在: %s", sourceDir)
	}
	if err := os.RemoveAll(outDir); err != nil {
		return body, fmt.Errorf("清理旧矩阵目录失败: %w", err)
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return body, fmt.Errorf("创建矩阵目录失败: %w", err)
	}
	graph := filepath.Join(outDir, "graph.json")
	findings := filepath.Join(outDir, "findings.json")
	bound := filepath.Join(outDir, "bound")
	importPath := filepath.Join(outDir, "import.json")
	// JavaParser 调用图按源码内容缓存；同一 commit 重试/重新准备时可直接复用，
	// 跳过大项目约 8 分钟的解析阶段。缓存损坏时会自动回退重跑。
	cacheDir := filepath.Join(s.m.dir, "cache", "callgraph")
	if err := os.MkdirAll(cacheDir, 0o755); err != nil {
		log.Printf("[matrix] 创建调用图缓存目录失败（继续无缓存）: %v", err)
		cacheDir = ""
	}
	buildArgs := []string{"matrix.graph.build", sourceDir, graph}
	if cacheDir != "" {
		buildArgs = append(buildArgs, "--cache-dir", cacheDir)
	}
	steps := [][]string{
		buildArgs,
		{"matrix.run", graph, "--analyzers", matrixAnalyzerList, "--out", findings},
		{"matrix.bind", graph, findings, bound},
		{"matrix.mkimport", bound + ".cells.json", bound + ".tasks.json", importPath},
	}
	for _, step := range steps {
		args := append([]string{"-m"}, step...)
		if err := s.runMatrixCommand(ctx, codeauditDir, python, args...); err != nil {
			return body, err
		}
	}
	raw, err := os.ReadFile(importPath)
	if err != nil {
		return body, fmt.Errorf("读取矩阵导入体失败: %w", err)
	}
	if err := json.Unmarshal(raw, &body); err != nil {
		return body, fmt.Errorf("解析矩阵导入体失败: %w", err)
	}
	return body, nil
}

// prepareTaskMatrix runs graph → analyzers → binder → import and seeds ca_cells.
// It is intentionally called only after the source tree has been attached and
// before the task is launched.

type scanProfile string

const (
	scanProfileQuick    scanProfile = "quick"
	scanProfileStandard scanProfile = "standard"
	scanProfileDeep     scanProfile = "deep"
)

func normalizeScanProfile(raw string) scanProfile {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case string(scanProfileQuick):
		return scanProfileQuick
	case string(scanProfileDeep):
		return scanProfileDeep
	default:
		return scanProfileStandard
	}
}

func scanProfileLabel(profile scanProfile) string {
	switch profile {
	case scanProfileQuick:
		return "快速"
	case scanProfileDeep:
		return "深度"
	default:
		return "标准"
	}
}

func highValueEndpoint(url string) bool {
	u := strings.ToLower(url)
	for _, word := range []string{
		"admin", "manage", "medicalrecord", "patient", "order", "pay", "refund",
		"register", "appointment", "doctor", "user", "permission", "role", "auth",
		"export", "download", "upload", "share", "record", "report", "account",
		"bill", "charge", "prescription", "病历", "支付", "挂号", "退款", "患者",
	} {
		if strings.Contains(u, word) {
			return true
		}
	}
	return false
}

func highValueSSRFPath(url string) bool {
	u := strings.ToLower(url)
	for _, word := range []string{
		"url", "uri", "redirect", "callback", "webhook", "proxy", "fetch",
		"download", "image", "file", "import", "notify", "request", "http",
	} {
		if strings.Contains(u, word) {
			return true
		}
	}
	return false
}

// scanProfileAllows decides whether an applicable cell enters this scan profile.
// The matrix still imports every cell (including N/A/unknown); filtered cells
// become unverified so the matrix remains visible but is not dispatched.
func scanProfileAllows(profile scanProfile, vuln, url string, priority int) bool {
	if profile == scanProfileDeep {
		return true
	}
	sensitive := highValueEndpoint(url)
	switch vuln {
	case "authz":
		// 标准档只对敏感业务接口做越权；快速档在敏感接口里再收敛到 P0/P1。
		if profile == scanProfileQuick {
			return sensitive && priority >= 14
		}
		return sensitive
	case "ssrf":
		if profile == scanProfileQuick {
			return priority >= 20 || (priority >= 14 && highValueSSRFPath(url))
		}
		return priority >= 14 || highValueSSRFPath(url)
	case "authn", "sql-injection", "file-upload", "path-traversal",
		"command-exec", "deserialization", "xxe", "secrets", "crypto",
		"dependency", "sensitive_data":
		return true
	default:
		if profile == scanProfileQuick {
			return priority >= 20 || (sensitive && priority >= 14)
		}
		return true
	}
}

func filterMatrixByScanProfile(body importCellsBody, profile scanProfile) importCellsBody {
	if profile == scanProfileDeep {
		return body
	}
	out := body
	out.Tasks = make([]db.CellInput, len(body.Tasks))
	copy(out.Tasks, body.Tasks)
	for i := range out.Tasks {
		cell := &out.Tasks[i]
		if cell.Eligibility != "applicable" {
			continue
		}
		if scanProfileAllows(profile, cell.VulnClass, cell.Endpoint.URL, cell.Priority) {
			continue
		}
		cell.Eligibility = "unverified"
		cell.Hold = false
		cell.Priority = 0
		cell.Bucket = "SKIP"
		cell.Reason = "未纳入" + scanProfileLabel(profile) + "扫描档位"
	}
	return out
}

func (s *Server) prepareTaskMatrix(ctx context.Context, t *Task, requireCells bool, profile scanProfile) (int, int, error) {
	if t == nil || strings.TrimSpace(t.SourcePath) == "" {
		return 0, 0, fmt.Errorf("任务没有源码目录")
	}
	sourceDir := filepath.Join(s.m.dir, filepath.FromSlash(t.SourcePath))
	if fi, err := os.Stat(sourceDir); err != nil || !fi.IsDir() {
		return 0, 0, fmt.Errorf("任务源码目录不存在: %s", sourceDir)
	}
	if err := normalizeSingleSourceRoot(sourceDir); err != nil {
		return 0, 0, fmt.Errorf("归一化源码目录失败: %w", err)
	}
	outDir := filepath.Join(s.m.dir, "tasks", t.ID, "matrix")
	body, err := s.buildMatrixImport(ctx, sourceDir, outDir)
	if err != nil {
		return 0, 0, err
	}
	body = filterMatrixByScanProfile(body, profile)
	if len(body.Tasks) == 0 && !requireCells {
		log.Printf("[matrix] task %s 没有可派发矩阵格，保留标准任务路径", t.ID)
		return 0, 0, nil
	}
	cells, seeded, err := s.importMatrixCells(t, body)
	if err != nil {
		return 0, 0, err
	}
	log.Printf("[matrix] task %s 导入 %d 格，生成 %d 个矩阵意图", t.ID, cells, seeded)
	return cells, seeded, nil
}

// normalizeSingleSourceRoot strips the common one-directory wrapper produced by
// local zip uploads (for example digital-smart-other/...). It only acts when the
// sole child looks like a project root, so a legitimate single top-level src/
// directory is left alone.
func normalizeSingleSourceRoot(dir string) error {
	ents, err := os.ReadDir(dir)
	if err != nil || len(ents) != 1 || !ents[0].IsDir() {
		return nil
	}
	wrapper := filepath.Join(dir, ents[0].Name())
	hasProjectMarker := false
	for _, name := range []string{"pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", filepath.Join("src", "main", "java")} {
		if _, err := os.Stat(filepath.Join(wrapper, name)); err == nil {
			hasProjectMarker = true
			break
		}
	}
	if !hasProjectMarker {
		return nil
	}
	children, err := os.ReadDir(wrapper)
	if err != nil {
		return err
	}
	for _, child := range children {
		from := filepath.Join(wrapper, child.Name())
		to := filepath.Join(dir, child.Name())
		if _, err := os.Stat(to); err == nil {
			continue
		}
		if err := os.Rename(from, to); err != nil {
			return err
		}
	}
	return os.Remove(wrapper)
}

func sourceHasJava(dir string) bool {
	found := false
	_ = filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil
		}
		if strings.HasSuffix(strings.ToLower(d.Name()), ".java") {
			found = true
			return filepath.SkipAll
		}
		return nil
	})
	return found
}

// prepareLocalUploadMatrix performs the one-time matrix preparation for a local
// upload. It returns hasJava=false when the task should keep the normal planner
// path. The caller owns the context and the task matrix_state transition.
func (s *Server) prepareLocalUploadMatrix(ctx context.Context, t *Task) (bool, error) {
	if t == nil || strings.TrimSpace(t.SourcePath) == "" {
		return false, nil
	}
	sourceDir := filepath.Join(s.m.dir, filepath.FromSlash(t.SourcePath))
	if fi, err := os.Stat(sourceDir); err != nil || !fi.IsDir() {
		return false, fmt.Errorf("任务源码目录不存在: %s", sourceDir)
	}
	if err := normalizeSingleSourceRoot(sourceDir); err != nil {
		return false, fmt.Errorf("归一化源码目录失败: %w", err)
	}
	if !sourceHasJava(sourceDir) {
		log.Printf("[matrix] task %s 没有 Java 源码，跳过矩阵流水线", t.ID)
		return false, nil
	}
	if _, _, err := s.prepareTaskMatrix(ctx, t, false, scanProfileDeep); err != nil {
		return true, err
	}
	return true, nil
}

// startLocalMatrixPreparation moves matrix generation off the create-task HTTP
// request. The task row exists immediately; startTask refuses to run while this
// background job is pending/running.
func (s *Server) startLocalMatrixPreparation(t *Task, autoStart bool) {
	if t == nil || strings.TrimSpace(t.SourcePath) == "" {
		return
	}
	if _, loaded := s.matrixJobs.LoadOrStore(t.ID, struct{}{}); loaded {
		return
	}
	_ = s.m.SetTaskMatrixState(t.ID, "pending", "")
	go func() {
		defer s.matrixJobs.Delete(t.ID)
		_ = s.m.SetTaskMatrixState(t.ID, "running", "")
		ctx, cancel := context.WithTimeout(s.ctx, 10*time.Minute)
		defer cancel()
		hasJava, err := s.prepareLocalUploadMatrix(ctx, t)
		if err != nil {
			_ = s.m.SetTaskMatrixState(t.ID, "failed", err.Error())
			log.Printf("[matrix] task %s 自动矩阵失败: %v", t.ID, err)
			return
		}
		state := "skipped"
		if hasJava {
			state = "ready"
		}
		_ = s.m.SetTaskMatrixState(t.ID, state, "")
		log.Printf("[matrix] task %s 自动矩阵准备完成: %s", t.ID, state)
		if autoStart {
			// Re-check the lifecycle: the user may have paused/deleted the task
			// while the matrix was being prepared.
			if cur, ok := s.m.Task(t.ID); ok && cur == t {
				life := cur.lifecycleSnapshot()
				if !life.Paused && !isTerminalStatus(life.Status) {
					s.launchTask(t, t.Description+" "+t.Goal, false)
				}
			}
		}
	}()
}

// recoverMatrixPreparations resumes background matrix jobs after a restart.
// It deliberately does not auto-start tasks; the user can open them manually.
func (s *Server) recoverMatrixPreparations() {
	for _, t := range s.m.List() {
		life := t.lifecycleSnapshot()
		if (life.MatrixState == "pending" || life.MatrixState == "running") && strings.TrimSpace(t.SourcePath) != "" {
			log.Printf("[matrix] 恢复任务 %s 的矩阵准备", t.ID)
			s.startLocalMatrixPreparation(t, false)
		}
	}
}
