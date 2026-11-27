# 0.2.0 发布验证

验证日期：2026-11-27。

- 19项单元与集成测试通过，覆盖图谱证据、检索、缓存、关系方向/极性、SVG和网络格式。
- 合成语料演示通过；本机可选igraph环境中实际使用Leiden构图。
- Python 3.13.5干净虚拟环境中，从wheel离线安装成功；未安装igraph、torch、sentence-transformers或Neo4j驱动。
- 干净环境中已安装的命令行入口完成构图、混合检索、SVG制图、GraphML/GEXF导出、离线Neo4j导出与关系表导入。
- 六个Skills格式校验通过，并在临时目录完成安装验证；没有覆盖使用者已有技能。
- 源码、wheel和sdist经过公开范围与内容检查：未包含私人研究归档、模型、受限抽取器、真实政策正文或凭据文件；未发现检查规则覆盖的凭据形态和个人主目录绝对路径。
- 公开源码ZIP包含逐文件SHA-256清单，构建时逐项核对压缩后的内容。

复查命令：`python3 -m unittest discover -s tests -v`、`sh run_demo.sh`、`python3 scripts/check_release.py`。GitHub Actions 结果见仓库 Actions 页面。
