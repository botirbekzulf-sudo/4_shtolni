FROM python:3.12-slim
WORKDIR /app
COPY server.py .
ENV PORT=8787 DATA_DIR=/data
VOLUME /data
EXPOSE 8787
CMD ["python", "-u", "server.py"]
