# Continuous Batching:推理引擎的吞吐基本功

> 来源:https://example.com/continuous-batching
> 2025 年 4 月

## 问题

朴素实现按请求整批处理:一个 batch 里所有序列一起前进,直到最短的那个结束,剩下全部 pad 等待。GPU 算力大量浪费在 padding 上,吞吐量被最长序列拖死。

## 解法:连续批处理

ORCA(2022)提出 continuous batching:迭代级别的调度——每生成一个 token,就把已完成的请求踢出 batch、把等待队列里的新请求插进来。batch 里永远是活跃序列,几乎没有 padding 浪费。这是 vLLM、TensorRT-LLM、TGI 等所有现代引擎的默认工作方式,通常带来 3-5 倍吞吐提升。

## 与 PagedAttention 的分工

连续批处理解决「batch 里放谁」的调度问题,PagedAttention 解决「KV 缓存放哪」的内存问题。两者正交,叠加生效。
