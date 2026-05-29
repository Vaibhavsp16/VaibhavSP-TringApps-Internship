output "cloudfront_url" {
  value = "https://${aws_cloudfront_distribution.cdn.domain_name}"
  description = "The URL of the CloudFront distribution for the static website."
}

output "origin_bucket_name" {
  value = aws_s3_bucket.origin.id
  description = "The name of the S3 bucket serving as the origin for the CloudFront distribution."
}

output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.cdn.id
  description = "The ID of the CloudFront distribution."
}