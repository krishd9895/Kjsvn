# Use the official Python image as the base image
FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . .

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port for the Telegram bot (not usually needed, but included for completeness)
EXPOSE 8080

# Run the Python script
CMD ["python", "main.py"]
