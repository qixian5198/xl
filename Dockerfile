# 情商口才训练工具 · 后端镜像
# 只打包代码和依赖；数据库(xl.db)和密钥(.env)在运行时挂载，不进镜像。
FROM python:3.11-slim

WORKDIR /app

# 先装依赖，利用构建缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用
COPY app ./app
COPY static ./static

# 数据落盘到挂载卷，避免重建镜像丢库
ENV DB_PATH=/data/xl.db
VOLUME /data

EXPOSE 8001

# 绑 0.0.0.0 方便容器端口映射；密钥等通过 env_file 注入
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
