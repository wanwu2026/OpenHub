FROM python:3.12-slim

WORKDIR /app

# 依赖单独一层，改代码不必重装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 数据在卷里，私钥由外部挂载，不进镜像层
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
