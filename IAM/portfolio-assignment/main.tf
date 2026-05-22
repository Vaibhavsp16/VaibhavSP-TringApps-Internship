provider "aws" {
  region = "us-east-1"
}

# 1. Create the S3 Bucket
resource "aws_s3_bucket" "portfolio_bucket" {
  bucket = "vaibhav-static-portfolio-1612" # <-- CHANGE THIS to make it globally unique
}

# 2. Turn on Static Website Hosting
resource "aws_s3_bucket_website_configuration" "portfolio_website" {
  bucket = aws_s3_bucket.portfolio_bucket.id

  index_document {
    suffix = "index.html"
  }
}

# 3. Disable the "Block Public Access" security feature
resource "aws_s3_bucket_public_access_block" "public_access" {
  bucket = aws_s3_bucket.portfolio_bucket.id

  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}

# 4. Attach a Bucket Policy allowing public read access
resource "aws_s3_bucket_policy" "public_read_access" {
  bucket = aws_s3_bucket.portfolio_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*" # The asterisk means "Anyone on the internet"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.portfolio_bucket.arn}/*"
      }
    ]
  })

  # Terraform must remove the security block BEFORE applying this policy
  depends_on = [aws_s3_bucket_public_access_block.public_access]
}

# 5. Upload the HTML file
resource "aws_s3_object" "index_html" {
  bucket       = aws_s3_bucket.portfolio_bucket.id
  key          = "index.html"
  source       = "index.html"
  content_type = "text/html" # This is crucial! It tells browsers to render it as a webpage, not download it as a file.
}

# 6. Output the final Website URL (Deliverable 1)
output "website_url" {
  value = aws_s3_bucket_website_configuration.portfolio_website.website_endpoint
}