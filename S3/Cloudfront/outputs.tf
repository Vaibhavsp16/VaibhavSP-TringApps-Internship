output "s3_bucket_name" {
  description = "The name of the S3 bucket created for CloudFront"
  value = aws_s3_bucket.origin.id
}

output "cloudfront_domain_name" {
  description = "The domain name of the CloudFront distribution"
  value = aws_cloudfront_distribution.cdn.domain_name
}