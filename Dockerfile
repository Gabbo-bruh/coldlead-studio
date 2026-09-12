# Dashboard in a container:  docker build -t coldlead . && docker run -p 8000:8000 -v coldlead:/data coldlead
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    COLDLEAD_HOME=/data

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir ".[all]" && useradd --create-home coldlead && mkdir -p /data && chown coldlead /data

USER coldlead
VOLUME ["/data"]
EXPOSE 8000
CMD ["coldlead", "web", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
