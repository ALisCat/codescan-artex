import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.FieldDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.ast.body.Parameter;
import com.github.javaparser.ast.body.VariableDeclarator;
import com.github.javaparser.ast.type.Type;
import com.github.javaparser.ast.expr.Expression;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;

import java.io.File;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CallGraphDump {
    static String esc(String s) {
        if (s == null) return "";
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                default: b.append(c);
            }
        }
        return b.toString();
    }

    static String className(Node n) {
        Optional<ClassOrInterfaceDeclaration> cd = n.findAncestor(ClassOrInterfaceDeclaration.class);
        if (cd.isPresent()) {
            return cd.get().getFullyQualifiedName().orElse(cd.get().getNameAsString());
        }
        return "";
    }

    static String methodId(MethodDeclaration md, String cls) {
        try {
            return md.resolve().getQualifiedSignature();
        } catch (Throwable t) {
            String ps = md.getParameters().stream()
                    .map(p -> p.getType().asString())
                    .collect(Collectors.joining(","));
            return cls + "." + md.getNameAsString() + "(" + ps + ")";
        }
    }

    static String resolveType(Type t) {
        try { return t.resolve().describe(); } catch (Throwable e) { return t.asString(); }
    }

    static String rel(File root, CompilationUnit cu) {
        try {
            String p = cu.getStorage().get().getPath().toString();
            return root.toPath().toAbsolutePath().relativize(Paths.get(p).toAbsolutePath()).toString();
        } catch (Throwable t) {
            return "";
        }
    }

    public static void main(String[] args) throws Exception {
        File root = new File(args[0]).getAbsoluteFile();
        String out = args[1];

        List<File> files = new ArrayList<File>();
        try (Stream<Path> s = Files.walk(root.toPath())) {
            s.filter(p -> p.toString().endsWith(".java") && !p.toString().contains("/target/"))
             .forEach(p -> files.add(p.toFile()));
        }
        Collections.sort(files);

        CombinedTypeSolver ts = new CombinedTypeSolver();
        ts.add(new ReflectionTypeSolver());
        // 关键：JavaParserTypeSolver 的根必须是源码根（src/main/java），不是项目根
        List<File> srcRoots = new ArrayList<File>();
        File smj = new File(root, "src/main/java");
        if (smj.isDirectory()) srcRoots.add(smj);
        File stj = new File(root, "src/test/java");
        if (stj.isDirectory()) srcRoots.add(stj);
        if (srcRoots.isEmpty()) srcRoots.add(root);
        for (File sr : srcRoots) ts.add(new JavaParserTypeSolver(sr));
        System.err.println("typeSolver roots=" + srcRoots);
        ParserConfiguration cfg = new ParserConfiguration()
                .setSymbolResolver(new JavaSymbolSolver(ts))
                .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17);
        JavaParser parser = new JavaParser(cfg);

        List<CompilationUnit> cus = new ArrayList<CompilationUnit>();
        for (File f : files) {
            ParseResult<CompilationUnit> pr = parser.parse(f);
            if (pr.isSuccessful() && pr.getResult().isPresent()) {
                cus.add(pr.getResult().get());
            } else {
                System.err.println("PARSE FAIL " + f + " " + pr.getProblems());
            }
        }
        System.err.println("files=" + files.size() + " parsed=" + cus.size());

        StringBuilder clb = new StringBuilder();
        boolean firstCl = true;
        for (CompilationUnit cu : cus) {
            String file = rel(root, cu);
            for (ClassOrInterfaceDeclaration cd : cu.findAll(ClassOrInterfaceDeclaration.class)) {
                String fqn = cd.getFullyQualifiedName().orElse(cd.getNameAsString());
                String ext = cd.getExtendedTypes().stream().map(t -> "\"" + esc(resolveType(t)) + "\"").collect(Collectors.joining(","));
                String impl = cd.getImplementedTypes().stream().map(t -> "\"" + esc(resolveType(t)) + "\"").collect(Collectors.joining(","));
                if (!firstCl) clb.append(",\n");
                firstCl = false;
                clb.append("{\"fqn\":\"").append(esc(fqn)).append("\",\"interface\":").append(cd.isInterface())
                   .append(",\"extends\":[").append(ext).append("],\"implements\":[").append(impl)
                   .append("],\"file\":\"").append(esc(file)).append("\"}");
            }
        }

        StringBuilder fb = new StringBuilder();
        boolean firstF = true;
        for (CompilationUnit cu : cus) {
            String file = rel(root, cu);
            for (FieldDeclaration fd : cu.findAll(FieldDeclaration.class)) {
                String cls = className(fd);
                for (VariableDeclarator v : fd.getVariables()) {
                    int line = v.getBegin().isPresent() ? v.getBegin().get().line : 0;
                    if (!firstF) fb.append(",\n");
                    firstF = false;
                    fb.append("{\"cls\":\"").append(esc(cls)).append("\",\"name\":\"").append(esc(v.getNameAsString()))
                      .append("\",\"type\":\"").append(esc(resolveType(v.getType())))
                      .append("\",\"file\":\"").append(esc(file)).append("\",\"line\":").append(line).append("}");
                }
            }
        }

        StringBuilder mb = new StringBuilder();
        boolean firstM = true;
        for (CompilationUnit cu : cus) {
            for (MethodDeclaration md : cu.findAll(MethodDeclaration.class)) {
                String cls = className(md);
                String id = methodId(md, cls);
                String file = rel(root, cu);
                int line = md.getBegin().isPresent() ? md.getBegin().get().line : 0;
                int endLine = md.getEnd().isPresent() ? md.getEnd().get().line : line;
                String params = md.getParameters().stream()
                        .map(p -> "\"" + esc(p.getType().asString()) + "\"")
                        .collect(Collectors.joining(","));
                if (!firstM) mb.append(",\n");
                firstM = false;
                mb.append("{\"id\":\"").append(esc(id)).append("\",\"cls\":\"").append(esc(cls))
                  .append("\",\"name\":\"").append(esc(md.getNameAsString()))
                  .append("\",\"file\":\"").append(esc(file)).append("\",\"line\":").append(line)
                  .append(",\"end\":").append(endLine)
                  .append(",\"params\":[").append(params).append("]}");
            }
        }

        StringBuilder cb = new StringBuilder();
        boolean firstC = true;
        int total = 0, resolved = 0, project = 0, projectResolved = 0;
        for (CompilationUnit cu : cus) {
            String file = rel(root, cu);
            for (MethodCallExpr mc : cu.findAll(MethodCallExpr.class)) {
                Optional<MethodDeclaration> callerOpt = mc.findAncestor(MethodDeclaration.class);
                if (!callerOpt.isPresent()) continue;
                MethodDeclaration caller = callerOpt.get();
                String callerId = methodId(caller, className(caller));
                String callee = "", scope = "";
                String scopeText = mc.getScope().isPresent() ? mc.getScope().get().toString() : "";
                boolean ok = false;
                try {
                    ResolvedMethodDeclaration r = mc.resolve();
                    callee = r.getQualifiedSignature();
                    scope = r.declaringType().getQualifiedName();
                    ok = true;
                    resolved++;
                } catch (Throwable t) {
                    try {
                        if (mc.getScope().isPresent()) {
                            Expression sc = mc.getScope().get();
                            scope = sc.calculateResolvedType().describe();
                        }
                    } catch (Throwable t2) { }
                }
                total++;
                boolean isProject = scope.startsWith("com.hezhan.");
                if (isProject) { project++; if (ok) projectResolved++; }
                int line = mc.getBegin().isPresent() ? mc.getBegin().get().line : 0;
                if (!firstC) cb.append(",\n");
                firstC = false;
                cb.append("{\"caller\":\"").append(esc(callerId))
                  .append("\",\"callee\":\"").append(esc(callee))
                  .append("\",\"scope\":\"").append(esc(scope))
                  .append("\",\"scopeText\":\"").append(esc(scopeText))
                  .append("\",\"name\":\"").append(esc(mc.getNameAsString()))
                  .append("\",\"file\":\"").append(esc(file)).append("\",\"line\":").append(line)
                  .append(",\"argc\":").append(mc.getArguments().size())
                  .append(",\"resolved\":").append(ok).append("}");
            }
        }

        try (PrintWriter w = new PrintWriter(out, "UTF-8")) {
            w.println("{");
            w.println("\"stats\":{\"files\":" + files.size() + ",\"parsed\":" + cus.size()
                    + ",\"calls\":" + total + ",\"resolved\":" + resolved
                    + ",\"project_calls\":" + project + ",\"project_resolved\":" + projectResolved + "},");
            w.println("\"classes\":[" + clb.toString() + "],");
            w.println("\"fields\":[" + fb.toString() + "],");
            w.println("\"methods\":[" + mb.toString() + "],");
            w.println("\"calls\":[" + cb.toString() + "]");
            w.println("}");
        }
        System.err.println("calls=" + total + " resolved=" + resolved
                + " project=" + project + " projectResolved=" + projectResolved);
    }
}
