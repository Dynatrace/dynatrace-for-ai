#!/usr/bin/env ruby
# Adds an SPM (Swift Package Manager) dependency to a target in an Xcode project.
#
# Uses the xcodeproj gem so UUIDs, project.pbxproj structure, and target
# linkage are handled correctly — no string manipulation of pbxproj.
#
# Usage: ruby add_spm_dependency.rb <project_path> <package_url> <min_version> <product_name> [target_name]
#   project_path   - Path to the .xcodeproj
#   package_url    - SPM package URL (e.g. https://github.com/Dynatrace/swift-mobile-sdk.git)
#   min_version    - Minimum version for upToNextMajorVersion (e.g. 8.0.0)
#   product_name   - SPM product name (e.g. Dynatrace or DynatraceSessionReplay)
#   target_name    - (Optional) Target name. If omitted, the first application target is used.
#
# Idempotent: re-running with the same arguments is a no-op.

require 'xcodeproj'

project_path = ARGV[0]
package_url  = ARGV[1]
min_version  = ARGV[2]
product_name = ARGV[3]
target_name  = ARGV[4]

if project_path.nil? || package_url.nil? || min_version.nil? || product_name.nil?
  abort "Usage: ruby add_spm_dependency.rb <project_path> <package_url> <min_version> <product_name> [target_name]"
end

project = Xcodeproj::Project.open(project_path)
target = if target_name
           project.targets.find { |t| t.name == target_name }
         else
           project.targets.find { |t| t.product_type == 'com.apple.product-type.application' }
         end

unless target
  abort "ERROR: Target '#{target_name || 'application target'}' not found in project #{project_path}"
end

# 1. Project-level package reference (XCRemoteSwiftPackageReference).
package_ref = project.root_object.package_references.find { |ref|
  ref.respond_to?(:repositoryURL) && ref.repositoryURL == package_url
}
unless package_ref
  package_ref = project.new(Xcodeproj::Project::Object::XCRemoteSwiftPackageReference)
  package_ref.repositoryURL = package_url
  package_ref.requirement = {
    'kind'     => 'upToNextMajorVersion',
    'minimumVersion' => min_version,
  }
  project.root_object.package_references << package_ref
  puts "Added package reference: #{package_url}"
else
  # Ensure version requirement matches what we were asked to set.
  expected = { 'kind' => 'upToNextMajorVersion', 'minimumVersion' => min_version }
  if package_ref.requirement != expected
    package_ref.requirement = expected
    puts "Updated package reference version: #{package_url} → #{min_version}"
  else
    puts "Package reference already present: #{package_url}"
  end
end

# 2. Target-level product dependency (XCSwiftPackageProductDependency).
product_dep = target.package_product_dependencies.find { |dep|
  dep.product_name == product_name && dep.package == package_ref
}
unless product_dep
  product_dep = project.new(Xcodeproj::Project::Object::XCSwiftPackageProductDependency)
  product_dep.package = package_ref
  product_dep.product_name = product_name
  target.package_product_dependencies << product_dep
  puts "Added product '#{product_name}' to target '#{target.name}'"
else
  puts "Product dependency '#{product_name}' already linked to target '#{target.name}'"
end

# 3. Frameworks build phase entry so the linker actually links it.
frameworks_has_dep = target.frameworks_build_phase.files.any? { |f|
  f.respond_to?(:product_ref) && f.product_ref == product_dep
}
unless frameworks_has_dep
  build_file = project.new(Xcodeproj::Project::Object::PBXBuildFile)
  build_file.product_ref = product_dep
  target.frameworks_build_phase.files << build_file
  puts "Added frameworks build phase entry for product '#{product_name}'"
end

project.save
puts "OK: project saved"
