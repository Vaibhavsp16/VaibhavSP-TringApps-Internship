provider "aws" {
  region = "us-east-1"
}

module "ec2_instance" {
  source              = "./modules/ec2_instance"
  ami_value           = "ami-0236922087fa98b6e"
  instance_type_value = "t2.micro"
  subnet_id_value     = "subnet-05b984bf6365e9262"
}