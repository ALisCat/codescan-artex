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

// prepareTaskMatrix runs graph → analyzers → binder → import and seeds ca_cells.
// It is intentionally called only after the source tree has been attached and
// before the task is launched.
func (s *Server) prepareTaskMatrix(ctx context.Context, t *Task) (int, int, error) {
	if t == nil || strings.TrimSpace(t.SourcePath) == "" {
		return 0, 0, fmt.Errorf("任务没有源码目录")
	}
	codeauditDir, err := s.codeauditDir()
	if err != nil {
		return 0, 0, err
	}
	python := s.matrixPython()
	if python == "" {
		return 0, 0, fmt.Errorf("找不到 python3，无法运行矩阵分析器")
	}
	sourceDir := filepath.Join(s.m.dir, filepath.FromSlash(t.SourcePath))
	if fi, err := os.Stat(sourceDir); err != nil || !fi.IsDir() {
		return 0, 0, fmt.Errorf("任务源码目录不存在: %s", sourceDir)
	}
	outDir := filepath.Join(s.m.dir, "tasks", t.ID, "matrix")
	if err := os.RemoveAll(outDir); err != nil {
		return 0, 0, fmt.Errorf("清理旧矩阵目录失败: %w", err)
	}
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return 0, 0, fmt.Errorf("创建矩阵目录失败: %w", err)
	}
	graph := filepath.Join(outDir, "graph.json")
	findings := filepath.Join(outDir, "findings.json")
	bound := filepath.Join(outDir, "bound")
	importPath := filepath.Join(outDir, "import.json")

	steps := [][]string{
		{"matrix.graph.build", sourceDir, graph},
		{"matrix.run", graph, "--analyzers", matrixAnalyzerList, "--out", findings},
		{"matrix.bind", graph, findings, bound},
		{"matrix.mkimport", bound + ".cells.json", bound + ".tasks.json", importPath},
	}
	for _, step := range steps {
		args := append([]string{"-m"}, step...)
		if err := s.runMatrixCommand(ctx, codeauditDir, python, args...); err != nil {
			return 0, 0, err
		}
	}
	raw, err := os.ReadFile(importPath)
	if err != nil {
		return 0, 0, fmt.Errorf("读取矩阵导入体失败: %w", err)
	}
	var body importCellsBody
	if err := json.Unmarshal(raw, &body); err != nil {
		return 0, 0, fmt.Errorf("解析矩阵导入体失败: %w", err)
	}
	cells, seeded, err := s.importMatrixCells(t, body)
	if err != nil {
		return 0, 0, err
	}
	log.Printf("[matrix] task %s 导入 %d 格，生成 %d 个矩阵意图", t.ID, cells, seeded)
	return cells, seeded, nil
}
