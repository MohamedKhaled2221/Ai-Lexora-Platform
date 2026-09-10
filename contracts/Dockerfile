FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY m1 ./m1
COPY tests ./tests
COPY contracts ./contracts
COPY templates ./templates

RUN pip install --no-cache-dir -e .

CMD ["python", "-m", "m1.demo"]
