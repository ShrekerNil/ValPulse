#!/usr/bin/env python3
"""
ValPulse 本地测试服务器
使用 Python 标准库启动 HTTP 服务，访问 reports/ 目录下内容。
运行方式：python serve.py
访问地址：http://localhost:8080/index.html
"""
import http.server
import socketserver
import pathlib

PORT = 8080
ROOT = pathlib.Path(r"D:\Repos\QLProjects\ValPulse\reports")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"ValPulse 测试服务器已启动: http://localhost:{PORT}/index.html")
        print(f"文件根目录: {ROOT.resolve()}")
        print("按 Ctrl+C 停止服务")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n服务已停止。")
