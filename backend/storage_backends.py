from storages.backends.s3boto3 import S3Boto3Storage


class DokumenS3Storage(S3Boto3Storage):
    default_acl        = 'private'
    file_overwrite     = False
    location           = 'dokumen'
    querystring_auth   = True
    querystring_expire = 300
    custom_domain      = None