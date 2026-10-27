FROM python:3.11-slim

WORKDIR /app

# 可选镜像源, 例如: --build-arg APT_MIRROR=mirrors.aliyun.com
#                   --build-arg PIP_MIRROR=https://mirrors.aliyun.com/pypi/simple/
ARG APT_MIRROR=""
ARG PIP_MIRROR=""

# Install system dependencies
RUN if [ -n "$APT_MIRROR" ]; then \
        sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
        sed -i "s|deb.debian.org|$APT_MIRROR|g" /etc/apt/sources.list; \
    fi \
    && apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir ${PIP_MIRROR:+-i $PIP_MIRROR} -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
