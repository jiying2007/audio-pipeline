#!/usr/bin/env ruby
# frozen_string_literal: true

# Offline parse-only validator for GitHub Actions run scripts.
# Workflow YAML parsing alone cannot catch a broken Bash scope command.
require 'psych'
require 'open3'
require 'timeout'

class WorkflowShellError < StandardError; end

module WorkflowShellSyntax
  module_function

  def mapping(node)
    return {} unless node.is_a?(Psych::Nodes::Mapping)
    node.children.each_slice(2).each_with_object({}) do |(key, value), result|
      result[key.value] = value if key.is_a?(Psych::Nodes::Scalar)
    end
  end

  def scalar(node)
    node.value if node.is_a?(Psych::Nodes::Scalar)
  end

  def shell_default(node)
    scalar(mapping(mapping(node)['run'])['shell'])
  end

  def default_shell(runner)
    names = if runner.is_a?(Psych::Nodes::Scalar)
              [runner.value]
            elsif runner.is_a?(Psych::Nodes::Sequence)
              runner.children.filter_map { |node| scalar(node) }
            else
              []
            end
    names.any? { |name| name.match?(/(?:ubuntu|macos|linux)/i) } ? 'bash' : nil
  end

  def parse_shell(run, shell, filename, job_name, step_name)
    return false unless shell.is_a?(String) && shell.match?(/\A(?:bash|sh)(?:\s|\z)/)
    command = shell.start_with?('bash') ? 'bash' : 'sh'
    raise WorkflowShellError, "overlong script #{filename}:#{job_name}/#{step_name}" if run.bytesize > 262_144
    begin
      _out, err, status = Timeout.timeout(10) { Open3.capture3(command, '-n', stdin_data: run) }
    rescue Timeout::Error
      raise WorkflowShellError, "shell syntax check timed out: #{filename}:#{job_name}/#{step_name}"
    end
    unless status.success?
      raise WorkflowShellError, "invalid #{command} run script at #{filename}:#{job_name}/#{step_name}: #{err.strip}"
    end
    true
  end

  def validate(source, filename)
    root = Psych.parse(source, filename: filename)&.root
    raise WorkflowShellError, "empty or invalid workflow #{filename}" unless root
    top = mapping(root)
    jobs = mapping(top['jobs'])
    checked = 0
    skipped = 0
    jobs.each do |job_name, job_node|
      job = mapping(job_node)
      steps = job['steps']
      next unless steps.is_a?(Psych::Nodes::Sequence)
      inherit = shell_default(job['defaults']) || shell_default(top['defaults'])
      inferred = default_shell(job['runs-on'])
      steps.children.each_with_index do |step_node, index|
        step = mapping(step_node)
        run = scalar(step['run'])
        next unless run
        shell = scalar(step['shell']) || inherit || inferred
        if parse_shell(run, shell, filename, job_name, scalar(step['name']) || "step#{index + 1}")
          checked += 1
        else
          skipped += 1
        end
      end
    end
    [checked, skipped]
  rescue Psych::Exception => e
    raise WorkflowShellError, "invalid workflow YAML #{filename}: #{e.message}"
  end

  def negative_example
    <<~'YAML'
      jobs:
        scope:
          runs-on: ubuntu-latest
          steps:
            - name: D1-scope
              shell: bash
              run: |
                set -euo pipefail
                changed="x"
                if grep -Eq '^(x|y) <<< "$changed" && <<< "$changed" &&
                  ! grep -Eq '^(z)$' <<< "$changed"; then
                  echo wrong
                fi
    YAML
  end

  def self_test
    good = <<~'YAML'
      jobs:
        scope:
          runs-on: ubuntu-latest
          steps:
            - name: D1-scope
              shell: bash
              run: |
                set -euo pipefail
                changed="x"
                if grep -Eq '^(x|y)$' <<< "$changed" &&
                  ! grep -Eq '^(z)$' <<< "$changed"; then
                  echo good
                fi
            - name: PowerShell-not-Bash
              shell: pwsh
              run: |
                Write-Output 'ok'
    YAML
    count, skipped = validate(good, 'valid.yml')
    raise WorkflowShellError, 'positive fixture did not scan Bash-only' unless count == 1 && skipped == 1
    begin
      validate(negative_example, 'regression.yml')
    rescue WorkflowShellError => e
      raise unless e.message.include?('invalid bash run script')
    else
      raise WorkflowShellError, 'historical broken Bash scope erroneously accepted'
    end
    custom = <<~'YAML'
      defaults:
        run:
          shell: sh
      jobs:
        job:
          runs-on: ubuntu-latest
          steps:
            - run: |
                if true; then echo ok; fi
    YAML
    raise WorkflowShellError, 'inherited shell not scanned' unless validate(custom, 'inherited.yml') == [1, 0]
    puts 'WORKFLOW_SHELL_SYNTAX_SELF_TEST_PASS'
  end
end

begin
  if ARGV == ['--self-test']
    WorkflowShellSyntax.self_test
  else
    raise WorkflowShellError, 'expected .github/workflows/*.yml paths' if ARGV.empty?
    total = skipped = 0
    ARGV.each do |path|
      file = File.read(path, encoding: 'UTF-8')
      raise WorkflowShellError, "workflow exceeds 1 MiB: #{path}" if file.bytesize > 1_048_576
      n, ignored = WorkflowShellSyntax.validate(file, path)
      total += n
      skipped += ignored
    end
    raise WorkflowShellError, 'no bash/sh run scripts scanned' if total.zero?
    puts "WORKFLOW_SHELL_SYNTAX_PASS checked=#{total} ignored_non_posix=#{skipped}"
  end
rescue WorkflowShellError => e
  warn "WORKFLOW_SHELL_SYNTAX_FAILED: #{e.message}"
  exit 1
end
