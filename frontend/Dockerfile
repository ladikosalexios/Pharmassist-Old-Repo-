FROM node:26-bookworm-slim

# Set the working directory inside the container
WORKDIR /usr/src/app

# Copy the application files
COPY . .

# Install dependencies
RUN npm install

# Expose the port the app runs on
EXPOSE 5173

# Start the React App
CMD ["npm", "run", "dev", "--", "--host"]