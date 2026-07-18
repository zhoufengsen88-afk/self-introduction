# M1 第四阶段：FastAPI SSE

本实验验证后端流式响应和前端流式消费的最小闭环，不接入真实 LLM。

## 验证目标

- FastAPI 通过 `text/event-stream` 返回流式响应。
- 事件格式固定为 `delta`、`done`、`error` 和 `cancelled`。
- 客户端能区分正常完成、服务端错误、服务端取消和客户端主动断开。
- 响应头关闭常见代理缓冲：`Cache-Control: no-cache`、`X-Accel-Buffering: no`。
- 浏览器示例使用 `fetch` + `ReadableStream` 消费 POST 响应。

## 运行

继续使用 M1 临时虚拟环境：

```bash
/tmp/self-introduction-m1-venv/bin/python -m pip install -r spikes/m1_sse/requirements.txt
/tmp/self-introduction-m1-venv/bin/python -m uvicorn spikes.m1_sse.app:app --reload --port 8010
```

打开：

```text
http://127.0.0.1:8010/
```

## 测试

```bash
/tmp/self-introduction-m1-venv/bin/python -m unittest discover -s spikes/m1_sse/tests -v
```

测试会启动一个临时 uvicorn 进程，验证真实 HTTP 流式响应，而不是只测函数调用。

## Fetch 客户端验证

启动服务后，可用 Node.js 的 Web Fetch / ReadableStream API 验证 POST 流式消费：

```bash
node spikes/m1_sse/fetch_client.mjs http://127.0.0.1:8010 normal
node spikes/m1_sse/fetch_client.mjs http://127.0.0.1:8010 error
node spikes/m1_sse/fetch_client.mjs http://127.0.0.1:8010 cancelled
node spikes/m1_sse/fetch_client.mjs http://127.0.0.1:8010 client-cancel
```

## 边界

本 Spike 不验证真实模型延迟、不验证部署平台代理行为，也不决定最终前端组件形态。它只固定后续 M2/M3 可以复用的流式事件语义。
