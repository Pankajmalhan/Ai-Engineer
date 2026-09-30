# google_cloudfunctions2_function has no --source-directory equivalent: Cloud
# Functions gen2 only accepts source as a GCS object (storage_source) or a Cloud
# Source Repository ref (repo_source), not a local path. `gcloud run deploy --source`
# hides exactly this step from you -- zip, upload, then reference the upload -- by
# doing it internally. A plain Terraform resource does not, so we do it ourselves.
data "archive_file" "function_source" {
  type        = "zip"
  source_dir  = "${path.module}/../function"
  output_path = "${path.module}/.build/function-source.zip"
  # Buildpacks (which build_config.runtime triggers) ignores a Dockerfile anyway, but
  # excluding it keeps this archive's *purpose* honest -- this is the buildpacks
  # source tree, not the Dockerfile one (function/Dockerfile is deploy_service.sh's).
  excludes = ["Dockerfile"]
}

resource "google_storage_bucket" "function_source" {
  name                        = "${var.project_id}-${var.function_name}-source"
  location                    = var.region
  uniform_bucket_level_access = true
  # This bucket only ever holds ephemeral build inputs, never anything a person
  # created directly -- safe to let `terraform destroy` remove it and its contents.
  force_destroy = true
}

resource "google_storage_bucket_object" "function_source" {
  # Content-hashed name: a source change produces a new object name, which is what
  # actually triggers google_cloudfunctions2_function to rebuild on the next apply
  # (Cloud Build reacts to a *new* storage_source.object, not to re-uploading the
  # same name with different bytes).
  name   = "function-source-${data.archive_file.function_source.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.function_source.output_path
}
