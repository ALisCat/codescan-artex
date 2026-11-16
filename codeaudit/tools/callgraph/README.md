# JavaParser 调用图 sidecar

不编译业务代码，只用 JavaParser 解析源码，导出：

- classes（extends / implements）
- fields（类型）
- methods（签名 / 参数 / 文件 / 起止行）
- calls（caller / callee / receiver / 实参个数 / 是否解析）
- scopeText（接收者源码文本，用于字段 → Mapper 推断）

## 依赖

`lib/` 下已带：

- javaparser-core 3.26.2
- javaparser-symbol-solver-core 3.26.2
- javassist 3.30.2-GA
- guava 33.2.1-jre
- failureaccess 1.0.2
- jsr305 3.0.2

## 编译

```bash
JAVA_HOME=/usr/lib/jvm/java-1.8.0-openjdk-1.8.0.492.b09-1.0.1.an8.x86_64
CP="lib/javaparser-core-3.26.2.jar:lib/javaparser-symbol-solver-core-3.26.2.jar:lib/javassist-3.30.2-GA.jar:lib/guava-33.2.1-jre.jar:lib/failureaccess-1.0.2.jar:lib/jsr305-3.0.2.jar"
$JAVA_HOME/bin/javac -cp "$CP" CallGraphDump.java
```

## 运行

```bash
$JAVA_HOME/bin/java -Xmx3g -cp "$CP:." CallGraphDump <源码根> <输出 callgraph.json>
```

图构建器会自动调用；也可手动指定：

```bash
cd codeaudit
python3 -m matrix.graph.build <源码根> <graph.json> --callgraph <已有 callgraph.json>
```

## 已知限制

- 没有依赖 jar 时，外部库调用大量 unresolved；工程内调用链仍可解析。
- Lombok 生成的 getter/setter 解析不到；`scopeText` + 字段类型作为 fallback。
- 方法解析因实参类型未解析失败时，图构建器用"接收者类型 + 方法名 + 参数个数"回退。
- MyBatis-Plus wrapper 没有字面 SQL；只记录 wrapper 调用点。
