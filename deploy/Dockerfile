FROM python:3.12-slim

# 非 root 运行：先建用户，再降权
RUN groupadd --system openhub && useradd --system --gid openhub --home-dir /app openhub

WORKDIR /app

# 依赖单独一层，改代码不必重装；装上 curl 供 healthcheck 使用
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssl curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 数据与卷属主交给非 root 用户；私钥由外部只读挂载，不进镜像层
RUN mkdir -p /app/data && chown -R openhub:openhub /app/data
VOLUME ["/app/data"]

USER openhub
EXPOSE 8080

# docker/容器编排自带重启与健康检查；应用层只管跑服务
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
