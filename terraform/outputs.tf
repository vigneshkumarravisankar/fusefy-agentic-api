output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.app.repository_url
}

output "alb_dns_name" {
  description = "DNS name of the load balancer"
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "Name of the ECS service"
  value       = aws_ecs_service.app.name
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = aws_cloudwatch_log_group.ecs.name
}

output "api_endpoints" {
  description = "API endpoints"
  value = {
    base_url    = "http://${aws_lb.main.dns_name}"
    health      = "http://${aws_lb.main.dns_name}/health"
    api_v1      = "http://${aws_lb.main.dns_name}/api/v1"
    docs        = "http://${aws_lb.main.dns_name}/docs"
    redoc       = "http://${aws_lb.main.dns_name}/redoc"
  }
}