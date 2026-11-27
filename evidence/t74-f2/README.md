# task-74 / T74-F2 会话附件（2026-11-27）

本目录是 [../t74-f2-session-20261127.md](../t74-f2-session-20261127.md) 的原始附件。

- run-2 是正式会话（22:08:45-22:20:31，GREEN）：session-results-run2.json、driver-run2.txt、
  serial-run2.txt、console-history-run2.txt、tcpdump-run2.txt、dnsmasq-run2.txt、http-run2.txt。
- run-1 是首轮 FAIL（22:00:19-22:05:41），失败来自驱动门禁缺陷（env 视图、T74 回读字数），
  保留为历史：session-results-run1.json、driver-run1.txt、serial-run1.txt。
- tool-e2631_t74_f2_session.py 是会话后修正版（env 有效视图、T74 16 字回读、F1 完整 32 位
  地址）；run-2 实际执行的版本见 driver-run2.txt 的命令序列。
- artifact-* 来自 CI run 46010298863 归档，用于钉住产物身份。
- *.txt 由 .gitattributes 标记为 -text，保留原始 CRLF/字节序列；SHA256SUMS.txt 是本目录校验清单。

