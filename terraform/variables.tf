variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "fastapi-app"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "container_port" {
  description = "Port exposed by the FastAPI container"
  type        = number
  default     = 8000  # FastAPI default port
}

variable "task_cpu" {
  description = "Fargate instance CPU units"
  type        = string
  default     = "512"  # Increased for Python app
}

variable "task_memory" {
  description = "Fargate instance memory"
  type        = string
  default     = "1024"  # Increased for Python app
}

variable "desired_count" {
  description = "Number of ECS tasks to run"
  type        = number
  default     = 2
}

variable "min_capacity" {
  description = "Minimum number of ECS tasks"
  type        = number
  default     = 1
}

variable "max_capacity" {
  description = "Maximum number of ECS tasks"
  type        = number
  default     = 10
}