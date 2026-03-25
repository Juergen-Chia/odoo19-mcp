FROM python:3.12-alpine

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY odoo_mcp_server.py .
COPY odoo_mcp_client.py .
COPY odoo_gradio_app.py .

# Expose Gradio port
EXPOSE 7860

# Create non-root user
RUN useradd -m -u 1000 odoo && \
    chown -R odoo:odoo /app
USER odoo

# Default command - run Gradio app
# To run MCP server instead: CMD ["python", "odoo_mcp_server.py", "--transport", "stdio"]
CMD ["python", "odoo_gradio_app.py"]
