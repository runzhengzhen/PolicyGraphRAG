# 贡献与发布

Python 3.9+。基础测试不需安装依赖：

```sh
python3 -m unittest discover -s tests -v
sh run_demo.sh
python3 scripts/check_release.py
```

新增真实语料、模型、图片或第三方代码前，确认公开范围和许可；不要提交密钥、私人数据、本机路径或研究缓存。修改行为时添加能验证证据、数据一致性或运行结果的测试。

贡献代码按项目 MIT 许可提交，第三方材料沿用各自许可。请在修改中说明实现与验证，不把未测接口写成已验证功能。

## 构建分发包

```sh
python3 -m pip install build
python3 -m build
python3 scripts/build_release.py
```

`dist/` 中分别是 Python wheel、源码发行包和带逐文件哈希清单的公开源码 ZIP。发布前可用 `python3 scripts/check_release.py --artifact dist/某个文件` 检查每个 ZIP、wheel 或 tar.gz。

可以上传这个公开源码包或将相同目录推送到自己的 Git 托管仓库。程序输出应另行筛选；不要同时上传本地完整研究归档、`data/` 或 `outputs/`。
