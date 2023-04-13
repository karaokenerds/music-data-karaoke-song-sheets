# Use the official Python base image
FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy the Pipfile and Pipfile.lock into the container
COPY Pipfile Pipfile.lock ./

# Install pipenv and the required packages
RUN pip install --no-cache-dir pipenv && \
    pipenv install --system --deploy --ignore-pipfile

# Copy the rest of the application code into the container
COPY . .

# Expose the port your application will run on
EXPOSE 5000

# Start the application
CMD ["python", "app.py"]
