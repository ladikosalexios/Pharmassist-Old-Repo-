FROM python:3.13-slim

# set a directory for the app
WORKDIR /usr/src/app

# copy all backend files to the container
COPY . .

# install dependencies
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Expose the port uvicorn will run on
EXPOSE 8000

# Start the server
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]