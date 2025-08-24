# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install build dependencies for certain python packages, if needed
# RUN apt-get update && apt-get install -y build-essential

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source code
COPY ./src /app/src
COPY ./frontend /app/frontend

# Ensure Python can import from /app/src
ENV PYTHONPATH=/app/src

# The command to run the application will be specified in docker-compose.yml
# This allows the same image to be used for both the api and worker services.
# The default command can be the API server.
CMD ["uvicorn", "mcbom.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
