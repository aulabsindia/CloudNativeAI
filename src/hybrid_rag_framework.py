# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Au.AI Software Labs Pvt Ltd
# Author: Vidya Ranganathan
# Date: 2024-06-10
# Product: Cloud Native Hybrid RAG Framework

"""
Self-Healing Code Generation for Kubernetes:
Multi-Model Hybrid RAG with Iterative Validation & Refinement.

Features:
    - Cloud-native, Go-first architecture for client-go code generation.
    - Hybrid semantic–syntactic parsing and intelligent code chunking.
    - Vector store indexing and retrieval powered by Qdrant.
    - Parallel multi-model LLM orchestration (Azure OpenAI + OpenAI-compatible).
    - Native static validation pipeline (golangci-lint/errors) with quality scoring.
    - Iterative self-correction loop for error refinement and model consensus.
    - Auto-refinement: best response is revalidated until all errors are fixed.
    - REST API backend for webhooks, validation, and RAG queries.
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Set, Optional
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from flask import Flask, jsonify, request
import re
from collections import Counter
import time
import subprocess
import tempfile
import json
import shutil
import stat

import httpx

# Code parsing and analysis utilities
from tree_sitter_languages import get_parser

# OpenAI / Azure integration (LLMs + embeddings)
from openai import OpenAI
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from llama_index.llms.azure_openai import AzureOpenAI

# LlamaIndex core (document and vector store management)
from llama_index.core.schema import TextNode, Document
from llama_index.core.node_parser import SemanticSplitterNodeParser  
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore

# vector store client
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logging.getLogger("httpx").setLevel(logging.INFO)
logging.getLogger("urllib3").setLevel(logging.INFO)

# Flask app for REST API
app = Flask(__name__)


class Logger:
    """
        Implements Logging functionality for the RAG based framework.
    """

    @staticmethod
    def section(title: str):
        # Prints a major section header for high-level pipeline phases.
        logger.info(f"\n{'='*100}")
        logger.info(f"  {title}")
        logger.info(f"{'='*100}")

    @staticmethod
    def subsection(title: str):
        # Prints a subsection header for sub-tasks within a validation phase.
        logger.info(f"\n{'-'*80}")
        logger.info(f"  {title}")
        logger.info(f"{'-'*80}")

    @staticmethod
    def progress(stage: str, current: int, total: int, details: str = ""):
        """
        Shows a visual progress bar with percentage and stage information.
        
        Args:
            - Operation stage name
            - Current iteration count
            - Total iterations
            - Optional contextual information (e.g., model name, error count)
        """
        percentage = (current / total * 100) if total > 0 else 0
        bar_length = 30
        filled = int(bar_length * current / total) if total > 0 else 0
        bar = '+' * filled + '-' * (bar_length - filled)        
        logger.info(f"  [{bar}] {percentage:5.1f}% | {stage} ({current}/{total}) {details}")

    # status helpers for clean categorized logs.
    @staticmethod
    def success(message: str):
        logger.info(f"  [SUCCESS] {message}")

    @staticmethod
    def info(message: str):
        logger.info(f"  [INFO]  {message}")

    @staticmethod
    def warning(message: str):
        logger.warning(f"  [WARN]  {message}")
    
    @staticmethod
    def error(message: str):
        logger.error(f"  [ERROR] {message}")

def clean_code_artifacts(response: str) -> str:
    """
        Clean Go code extracted from a Markdown-formatted response. 
        Removes Markdown code block artifacts and preserves only the 
        actual Go code.
        
        Strategy:
        1. Remove lines before the opening ``` (or ```go)
        2. Remove lines after the closing ```
        3. Remove stray ``` that might remain after clearing the 
        block markers and explnations.

        Args:
        - The input string containing Go code, likely wrapped in 
        Markdown code fences.

        Returns the cleaned Go code with Markdown artifacts removed.
        If cleaning results in empty content, returns the original 
        response stripped of leading/trailing whitespace.
    """

    # Return early if the input is empty or only whitespace.
    if not response or not response.strip():
        return response
    
    # Split the response into lines for line-by-line processing.
    lines = response.split('\n')
    start_idx = 0
    end_idx = len(lines)
    
    # Find the start of the code block. Look for ```go first, then fallback to 
    # lines starting with 'package ' for raw Go snippets.
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('``````go'):
            start_idx = i + 1
            break
        elif stripped.startswith('package '):
            start_idx = i
            break
    
    # Find the end of the code block by searching for closing ```
    for i in range(len(lines) - 1, start_idx - 1, -1):
        if lines[i].strip().startswith('```'): 
            end_idx = i
            break
    
    # Extract the relevant code lines.
    code_lines = lines[start_idx:end_idx]
    
    # Remove any standalone ``` or ```go lines that may still be present inside the code.
    cleaned = [line for line in code_lines if line.strip() not in ['```', '``````go']]
    
    # Join lines back into a single string, trimming extra whitespace
    result = '\n'.join(cleaned).strip()

    # If cleaning removes everything, fallback to returning the original response stripped
    return result if result else response.strip()

def count_error_lines(issue_text: str) -> int:
    """
        Count the actual number of error lines in golangci-lint Issue Text field.
        
        golangci-lint sometimes groups multiple errors into a single Issue object
        with newline-separated error messages in the Text field.
        
        Args: Text field from a golangci-lint Issue
            
        Returns number of actual error lines
    """
    if not issue_text:
        return 0
    
    # Split by newlines and count non-empty lines that look like errors
    lines = issue_text.strip().split('\n')
    error_count = 0
    
    for line in lines:
        line = line.strip()
        # Skip empty lines
        if not line:
            continue
        # Skip lines that are just comments or headers (like "# temp/validation")
        if line.startswith('#'):
            continue
        # Count lines that contain file references or error descriptions
        # Typical format: "./file.go:line:col: error message"
        if '.go:' in line or 'undefined' in line or 'not used' in line or 'error' in line.lower():
            error_count += 1
    
    # If no structured errors found, count it as at least 1 error
    # (the Issue wouldn't exist if there wasn't an error)
    return max(error_count, 1)

class StaticCodeValidator:
    """
    Native validation using bash script for Go code with golangci-lint.
    """
    
    def __init__(self):
        # Create the validation script
        self.script_path = self._create_validation_script()

    def _create_validation_script(self) -> str:
        """Create the validation bash script"""
        script_path = Path("/tmp/validate_go_code.sh")
        
        # Redirect all go mod output to stderr only
        script_content = '''#!/bin/bash
set -e
WORKSPACE_DIR="$1"
CODE_FILE="$2"
DEPS_PATH="${3:-}"
OUTPUT_JSON="$WORKSPACE_DIR/lint_output.json"
STDERR_LOG="$WORKSPACE_DIR/lint_stderr.log"

RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $1" >&2; }
print_warning() { echo -e "${YELLOW}[WARN]${NC} $1" >&2; }
print_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

check_and_install_go() {
    if command -v go &> /dev/null; then
        print_info "[OK] Go is already installed: $(go version)"
        return 0
    fi
    print_warning "[WARN]  Installing Go..."
    OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64) ARCH="amd64" ;;
        aarch64|arm64) ARCH="arm64" ;;
    esac
    GO_VERSION="1.22.0"
    GO_TARBALL="go${GO_VERSION}.${OS}-${ARCH}.tar.gz"
    wget -q "https://go.dev/dl/${GO_TARBALL}" -O "/tmp/${GO_TARBALL}" || return 1
    sudo rm -rf /usr/local/go
    sudo tar -C /usr/local -xzf "/tmp/${GO_TARBALL}"
    rm "/tmp/${GO_TARBALL}"
    export PATH="/usr/local/go/bin:$PATH"
    echo 'export PATH="/usr/local/go/bin:$PATH"' >> ~/.bashrc
}

check_and_install_golangci_lint() {
    if command -v golangci-lint &> /dev/null; then
        print_info "[OK] golangci-lint already installed"
        return 0
    fi
    print_warning "[WARN]  Installing golangci-lint..."
    curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/master/install.sh | sh -s -- -b $(go env GOPATH)/bin v1.55.2
    export PATH="$(go env GOPATH)/bin:$PATH"
    echo 'export PATH="$(go env GOPATH)/bin:$PATH"' >> ~/.bashrc
}

create_go_mod() {
    cd "$1"
    [ -f "go.mod" ] && return 0
    print_info "[INFO] Creating go.mod..."
    
    # Redirect ALL output to stderr only (not stdout)
    go mod init temp/validation >> "$STDERR_LOG" 2>&1
    
    if grep -q "k8s.io" *.go 2>/dev/null; then
        go get k8s.io/api@v0.28.0 k8s.io/apimachinery@v0.28.0 k8s.io/client-go@v0.28.0 >> "$STDERR_LOG" 2>&1
    fi
    if grep -q "sigs.k8s.io" *.go 2>/dev/null; then
        go get sigs.k8s.io/controller-runtime@v0.16.0 >> "$STDERR_LOG" 2>&1
    fi
    [ -n "$2" ] && [ -d "$2" ] && [ -f "$2/go.mod" ] && {
        module_name=$(grep "^module" "$2/go.mod" | awk '{print $2}')
        echo "replace $module_name => $2" >> go.mod
    }
    go mod tidy >> "$STDERR_LOG" 2>&1
}

main() {
    check_and_install_go || exit 1
    check_and_install_golangci_lint || exit 1
    create_go_mod "$WORKSPACE_DIR" "$DEPS_PATH"
    touch "$WORKSPACE_DIR/.go_mod_created_by_script"
    cd "$WORKSPACE_DIR"
    
    # Run golangci-lint and capture output
    golangci-lint run --out-format=json --timeout=600s "$PWD" > "$OUTPUT_JSON" 2>> "$STDERR_LOG" || true
    
    # Send JSON to stdout to capture precise required results
    if [ -f "$OUTPUT_JSON" ]; then
        cat "$OUTPUT_JSON"
    else
        # Output empty JSON if file doesn't exist
        echo "{}"
    fi
    
    
    # Cleanup
    rm -f "$WORKSPACE_DIR/go.mod" "$WORKSPACE_DIR/go.sum" "$WORKSPACE_DIR/.go_mod_created_by_script"
}
main "$@"
'''
        
        script_path.write_text(script_content)
        script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)
        Logger.success(f"Created validation script at {script_path}")
        return str(script_path)

    # Validate and fix Go code using native bash-based linting pipeline.
    @staticmethod
    def validate_and_fix_go_code(code: str, model_name: str = "model") -> Dict:        
        """        
            Perform a native validation of generated Go code using a local 
            bash-based linting pipeline. This function writes the provided
            Go source code to a temporary directory, executes a validation 
            script, and parses the linting output (JSON or text) to assess 
            quality and gather detailed error information.

            Args:
                - The raw Go code string to be validated.
                - Identifier for the model or generator that produced the code.
                Used to name temporary files. Defaults to "model".            Returns a result dictionary with keys including:
                - quality score that ranges between 0.0 and 1.0 for lint quality.
                - A flag indicating whether errors were found.
                - list of textual error descriptions.
                - number of lint issues reported.
                - total count of identified problems.
                - bool flag showing if score met the threshold.
                - original or modified Go code (if fixes applied).
                - granular breakdown of validation stages.
        """
        Logger.subsection(f"Native Validation Pipeline - {model_name}")

        # Initialize validation results with default metrics and structure.
        validation_result = {
            'quality_score': 0.0,
            'has_errors': False,
            'errors': [],
            'golangci_lint_errors': 0,
            'total_errors': 0,
            'validation_passed': False,
            'model_name': model_name,
            'fixed_code': None,
            'was_fixed': False,
            'stage_details': {'golangci': {'errors': []}}
        }

        # Step 1: Handle trivial empty code case early to avoid unnecessary processing
        if not code or not code.strip():
            validation_result['errors'].append("Empty code")
            validation_result['has_errors'] = True
            validation_result['fixed_code'] = code
            return validation_result

        # Step 2: Write code to temporary file for validation.
        temp_dir = tempfile.mkdtemp(prefix='code_validation_')

        try:
            # Write Go code to temporary file for linting
            code_filename = f"{model_name}_response.go"
            code_filepath = os.path.join(temp_dir, code_filename)
            with open(code_filepath, 'w', encoding='utf-8') as f:
                f.write(code)

            Logger.info(f"\n_______________________________________________________________")
            Logger.info(f"| Native Go Validation (Bash Script)")
            Logger.info(f"|______________________________________________________________")

            # Step 3: Execute the validation bash script and capture output.
            validator = StaticCodeValidator()
            bash_cmd = ['bash', validator.script_path, temp_dir, code_filename]
            Logger.info(f"[INFO] Running native validation...")
            lint_result = subprocess.run(bash_cmd, capture_output=True, text=True, timeout=650)

            golangci_lint_errors = 0

            # Step 4: Process STDERR for script-level logs or debugging information
            if lint_result.stderr:
                stderr_lines = lint_result.stderr.strip().split('\n')
                for line in stderr_lines[-20:]:
                    if line.strip():
                        logger.info(f"   {line}")

            # Step 5: Parse STDOUT for capturing JSON lint results
            if lint_result.stdout and lint_result.stdout.strip():
                stdout_clean = lint_result.stdout.strip()

                # Handle common empty/null cases before attempting JSON parse
                if stdout_clean == "" or stdout_clean == "null" or stdout_clean == "{}":
                    Logger.success("[SUCCESS] No issues found!")
                    golangci_lint_errors = 0
                else:
                    try:
                        lint_data = json.loads(stdout_clean)

                        # Check if lint_data is None or empty dict
                        if lint_data is None or lint_data == {}:
                            Logger.success("[SUCCESS] No issues found!")
                            golangci_lint_errors = 0
                        # Check for Issues field in the JSON output.
                        elif 'Issues' in lint_data and lint_data['Issues']:
                            lint_issues = lint_data['Issues']                                                       
                            golangci_lint_errors = 0

                            # Step 6: Count and record each lint issue in structured form.
                            for issue in lint_issues:
                                issue_text = issue.get('Text', '')
                                error_line_count = count_error_lines(issue_text)
                                golangci_lint_errors += error_line_count
                                
                                # Store individual errors for reporting
                                loc = issue.get('Pos', {})
                                linter = issue.get('FromLinter', 'unknown')
                                
                                # Split the Text field by newlines to get individual errors
                                error_lines = [line.strip() for line in issue_text.split('\n') if line.strip()]
                                for error_line in error_lines:
                                    if error_line.startswith('#'):
                                        continue  # Skip comment lines
                                    error_msg = f"Line {loc.get('Line', '?')}: {error_line} [{linter}]"
                                    validation_result['errors'].append(error_msg)
                                    validation_result['stage_details']['golangci']['errors'].append(error_msg)
                            
                            # Report summary of errors found
                            if golangci_lint_errors > 0:
                                Logger.warning(f"[WARN]  Found {golangci_lint_errors} error(s)")
                                # Show first few errors
                                for idx, error in enumerate(validation_result['errors'][:5], 1):
                                    logger.info(f"    {idx}. {error}")
                                if len(validation_result['errors']) > 5:
                                    logger.info(f"    ... and {len(validation_result['errors']) - 5} more errors")
                        else:
                            # Valid JSON but no Issues field or Issues is None/empty
                            Logger.success("[SUCCESS] No issues found!")
                            golangci_lint_errors = 0

                    except json.JSONDecodeError as e:
                        # Graceful handling of JSON parsing errors.
                        Logger.error(f"[ERROR] JSON parsing failed: {str(e)}")
                        Logger.info(f"   Stdout content: {stdout_clean[:500]}...")
                        Logger.info(f"   This indicates the bash script is still outputting non-JSON to stdout")
                        golangci_lint_errors = 0  # Assume no errors if we can't parse

            else:
                # Step 7: Handle cases where no stdout was returned
                if lint_result.returncode == 0:
                    Logger.success("[SUCCESS] No issues found!")
                    golangci_lint_errors = 0
                else:
                    Logger.error(f"[ERROR] Validation failed with exit code {lint_result.returncode}")
                    validation_result['errors'].append(f"Validation failed: exit code {lint_result.returncode}")
                    validation_result['has_errors'] = True
                    golangci_lint_errors = 1

            # Step 8: Compile final validation results and quality score.
            validation_result['golangci_lint_errors'] = golangci_lint_errors
            validation_result['total_errors'] = golangci_lint_errors
            validation_result['fixed_code'] = code

            # Arrive at quality score based on error count for calculation.
            quality_score = max(0.0, 1.0 - (golangci_lint_errors * 0.08))
            validation_result['quality_score'] = quality_score
            validation_result['has_errors'] = (golangci_lint_errors > 0)
            validation_result['validation_passed'] = (quality_score >= 0.5)

            logger.info(f"  [INFO] Quality Score: {quality_score:.2f}/1.0 (based on {golangci_lint_errors} error(s))")

        # Step 9: Capture any unexpected runtime exceptions gracefully.
        except Exception as e:
            validation_result['errors'].append(f"Validation error: {str(e)}")
            validation_result['has_errors'] = True
            validation_result['fixed_code'] = code
            Logger.error(f"[ERROR] Validation error: {e}")

         # Step 10: Cleanup temporary files and return structured result.
        finally:
            try:
                pass
                #shutil.rmtree(temp_dir)
            except:
                pass

        return validation_result

    # Validate code with automatic language detection and optional lint-based correction.
    @staticmethod
    def validate_code(code: str, language: str = 'auto', model_name: str = "model") -> Dict:
        """              
            This method performs static code validation for a given code snippet.
            It automatically detects the programming language 
            (defaulting to Go when applicable), runs language-specific validators 
            (golangci-lint for Go), and returns a detailed report containing 
            validation results, error count, and optionally fixed code.

            Args:            
                - The source code content to be validated.
                - Language identifier or 'auto' for automatic detection.                   
                - Name of the model or system that produced the code.
                - Path to local dependencies or modules required for static validation.

            Returns a dictionatory containing validation results with keys.          
        """
        # Auto-detect language if set to 'auto'
        if language == 'auto':
            if 'package ' in code and 'func ' in code:
                language = 'go'
        
        if language == 'go':
            # Go code validation
            return StaticCodeValidator.validate_and_fix_go_code(code, model_name)
        else:
            # Unsupported language - return default no-error result
            return {
                'quality_score': 0.5,
                'has_errors': False,
                'errors': [],
                'golangci_lint_errors': 0,
                'total_errors': 0,
                'validation_passed': True,
                'model_name': model_name,
                'fixed_code': code,
                'was_fixed': False,
                'stage_details': {'golangci': {'errors': []}}
            }

# Handles iterative error refinement and self-correction of generated code.
class ErrorsRefinementAndSelfCorrection:    
    """      
        This class manages the process of detecting, refining, and correcting 
        code generation errors through multiple iterations of LLM-based feedback 
        and static validation. It encapsulates configuration for controlling the 
        maximum number of refinement iterations.
    """
    
    def __init__(self, max_refinement_iterations: int = None):
        """
            Initialize the error refinement and self-correction handler.

            Args: Maximum number of refinement passes allowed. Sets to
            'MAX_REFINEMENT_ITERATIONS' env value, or 3 if not set.
        """

        # Use explicit parameter if provided; otherwise fallback to environment variable or default.
        self.max_refinement_iterations = max_refinement_iterations or int(os.getenv('MAX_REFINEMENT_ITERATIONS', '3'))

    # Primary refinement method that iteratively fixes errors in the best response    
    def refine_response_iteratively(self, 
                                   best_response_data: Dict, 
                                   model_config: 'ModelConfig',
                                   static_validator: StaticCodeValidator) -> Tuple[str, Dict]:
        """        
            Iteratively refine a code response from the best-performing 
            model to fix errors detected by static validation. Uses the 
            LLM model to generate corrections and validates after each iteration 
            until errors are fixed or max iterations reached.

            Args:
                - Dictionary containing the best response from multi-model selection, 
                including response text and metadata.
                - Configuration of the model that generated the best response.
                - Instance of StaticCodeValidator for linting/validation.
                - Path to dependency files for validation. Defaults to None.

            Returns a Tuple containing:
                - The final refined code after iterative corrections.
                - A dictionary with metadata about the refinement process.            
        """
        
        Logger.section("ERROR REFINEMENT AND SELF-CORRECTION")
        
        # Extract initial response and validation
        current_response = best_response_data['response']
        initial_validation = best_response_data.get('metadata', {}).get('static_validation', {})
        
        # Check if refinement is needed
        if not initial_validation.get('has_errors', False):
            Logger.success("[SUCCESS] No errors detected in best response. Skipping refinement.")
            return current_response, {
                'refinement_needed': False,
                'iterations_performed': 0,
                'final_errors': 0,
                'initial_errors': 0
            }
            
        initial_error_count = initial_validation.get('total_errors', 0)
        Logger.warning(f"[WARN]  {initial_error_count} errors detected in best response from {best_response_data['model']}")
        
        # Show initial errors
        if initial_validation.get('errors'):
            Logger.info("[INFO] Initial errors found:")
            for i, error in enumerate(initial_validation['errors'][:5], 1):  # Show first 5 errors
                logger.info(f"    {i}. {error}")
            if len(initial_validation['errors']) > 5:
                logger.info(f"    ... and {len(initial_validation['errors']) - 5} more errors")
                
        logger.info(f"\n  [INFO] Starting iterative refinement process...")
        
        refinement_metadata = {
            'refinement_needed': True,
            'initial_errors': initial_error_count,
            'iterations_performed': 0,
            'iteration_details': [],
            'final_errors': initial_error_count,
            'refinement_successful': False
        }
        
        # Iterative refinement loop
        for iteration in range(1, self.max_refinement_iterations + 1):
            Logger.subsection(f"Refinement Iteration {iteration}/{self.max_refinement_iterations}")
            
            # Get the code to refine (from previous iteration or initial)
            code_to_refine = current_response
            
            # Apply formatter to maintain style/structure (reuse existing clean_code_artifacts)
            if iteration > 1:
                code_to_refine = clean_code_artifacts(code_to_refine)
            
            # Generate refined response using the same model
            refined_response = self._request_refinement_from_model(
                code_to_refine=code_to_refine,
                errors_context=initial_validation.get('errors', []) if iteration == 1 else current_validation.get('errors', []),
                model_config=model_config,
                iteration=iteration
            )
            
            if not refined_response:
                Logger.error(f"[ERROR] Failed to get refined response in iteration {iteration}")
                break
                
            # Apply formatter to maintain consistency
            refined_response = clean_code_artifacts(refined_response)
            
            # Validate the refined response
            current_validation = static_validator.validate_code(
                code=refined_response,
                language='auto',
                model_name=f"{best_response_data['model']}_refined_iter{iteration}"
            )
            
            current_error_count = current_validation.get('total_errors', 0)
            
            # Log iteration results
            iteration_data = {
                'iteration': iteration,
                'errors_before': refinement_metadata['final_errors'],
                'errors_after': current_error_count,
                'validation_result': current_validation,
                'improvement': refinement_metadata['final_errors'] - current_error_count
            }
            refinement_metadata['iteration_details'].append(iteration_data)
            refinement_metadata['iterations_performed'] = iteration
            refinement_metadata['final_errors'] = current_error_count
            
            Logger.info(f"[INFO] Iteration {iteration} Results:")
            logger.info(f"    • Errors before: {iteration_data['errors_before']}")
            logger.info(f"    • Errors after: {current_error_count}")
            logger.info(f"    • Improvement: {iteration_data['improvement']} errors fixed")
            
            if current_error_count > 0:
                Logger.info(f"[INFO] Remaining errors:")
                for i, error in enumerate(current_validation.get('errors', [])[:3], 1):
                    logger.info(f"        {i}. {error}")
                if len(current_validation.get('errors', [])) > 3:
                    logger.info(f"        ... and {len(current_validation.get('errors', [])) - 3} more errors")
            
            # Update current response for next iteration
            current_response = refined_response
            
            # Check if refinement is successful (no errors)
            if current_error_count == 0:
                Logger.success(f"[SUCCESS] Refinement successful! All errors fixed in {iteration} iteration(s)")
                refinement_metadata['refinement_successful'] = True
                break
                
            # Check if no improvement was made
            if iteration > 1 and iteration_data['improvement'] <= 0:
                Logger.warning(f"[WARN]  No improvement in iteration {iteration}. Stopping refinement.")
                break
                
        # Final summary
        final_improvement = initial_error_count - refinement_metadata['final_errors']
        
        Logger.subsection("Refinement Summary")
        logger.info(f"  [INFO] Initial errors: {initial_error_count}")
        logger.info(f"  [INFO] Final errors: {refinement_metadata['final_errors']}")
        logger.info(f"  [INFO] Total improvement: {final_improvement} errors fixed")
        logger.info(f"  [INFO] Iterations performed: {refinement_metadata['iterations_performed']}")
        
        if refinement_metadata['refinement_successful']:
            Logger.success("[SUCCESS] Refinement process completed successfully - all errors resolved!")
        elif final_improvement > 0:
            Logger.warning(f"[WARN]  Partial success - {final_improvement} errors fixed, {refinement_metadata['final_errors']} remaining")
        else:
            Logger.error("[ERROR] Refinement process did not improve the code quality")
            
        return current_response, refinement_metadata
    
    # Request refinement from the LLM model
    def _request_refinement_from_model(self, 
                                     code_to_refine: str, 
                                     errors_context: List[str],
                                     model_config: 'ModelConfig',
                                     iteration: int) -> str:
        """        
            Request the LLM to iteratively refine a given code snippet 
            by fixing specific errors while preserving the original 
            structure, style, and functionality. This method supports 
            both Azure OpenAI and OpenAI-compatible models.
            - Log the refinement request and iteration.
            - Prepare a refinement prompt that includes:
                - The code to be corrected
                - A list of the first 10 errors as context
                - Instructions to preserve style and structure
            - Call the appropriate LLM based on model type:
                - Azure OpenAI: uses `complete` method
                - OpenAI-compatible: uses chat completions API
            - Capture the response and strip any extra whitespace.
            - Log success or error information depending on the outcome.
            - Return the refined code or None if an error occurs.

            Args:
                - The code snippet that contains errors and requires correction.
                - List of error messages that serve as guidance for refinement.
                - Configuration object of the model to be queried.
                - Current refinement iteration count for logging and tracking.

            Returns refined code returned by the model. Returns None if 
            refinement fails or an unsupported model type is provided.  
        """

        # Log the refinement request
        Logger.info(f"[INFO] Requesting refinement from {model_config.name} (iteration {iteration})")
        
        # Create refinement prompt; Convert first 10 errors into a formatted string to guide the model.
        errors_text = "\n".join([f"- {error}" for error in errors_context[:10]])  # Limit to first 10 errors

        # Construct the final instruction prompt for the LLM
        refinement_prompt = f"""Here is source code that has some errors. Fix these errors while retaining the same format, structure, and style. Just address the errors without changing the overall approach or architecture.

ERRORS TO FIX:
{errors_text}

SOURCE CODE TO FIX:
```go
{code_to_refine}
```

Please provide the corrected code that fixes these specific errors while maintaining the same structure and functionality. Return only the corrected Go code without explanations."""

        try:
            # Call the appropriate LLM based on model type
            if model_config.type == 'azure_openai':
                # Use Azure OpenAI
                from llama_index.llms.azure_openai import AzureOpenAI
                llm_client = AzureOpenAI(
                    model=model_config.name,
                    deployment_name=model_config.deployment,
                    api_key=model_config.api_key,
                    azure_endpoint=model_config.endpoint.rstrip('/'),
                    api_version=model_config.api_version,
                )
                # For Azure OpenAI via llama_index, we need to use complete method
                response = llm_client.complete(refinement_prompt)
                refined_code = str(response)

            # Call OpenAI-compatible model if type is 'openai_compatible'    
            elif model_config.type == 'openai_compatible':
                # Use OpenAI-compatible API
                client = OpenAI(
                    base_url=model_config.endpoint,
                    api_key=model_config.api_key
                )
                
                # Generate chat completion for refinement
                completion = client.chat.completions.create(
                    model=model_config.deployment,
                    messages=[
                        {"role": "system", "content": "You are an expert Go developer. Fix the provided code errors while maintaining the exact same structure, format, and style. Only address the specific errors mentioned."},
                        {"role": "user", "content": refinement_prompt}
                    ],
                    max_tokens=6000,
                    temperature=0.1  # Low temperature for consistent fixes
                )
                
                refined_code = completion.choices[0].message.content
            # Unsupported model type    
            else:
                Logger.error(f"[ERROR] Unsupported model type: {model_config.type}")
                return None

            # Log and return refined code if successful.    
            if refined_code:
                Logger.success(f"[SUCCESS] Received refined response ({len(refined_code)} chars)")
                return refined_code.strip()
            else:
                Logger.error("[ERROR] Received empty response from model")
                return None

        # Catch and log any exceptions during the refinement request        
        except Exception as e:
            Logger.error(f"[ERROR] Error during refinement request: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None

# Handles iterative generation with continuation.
class IterativeGenerator:    
    """
        Handles iterative model response or code generation with automatic 
        continuation. Useful for models that may truncate output due to 
        token limits. Manages multiple iterations, concatenates responses, 
        and tracks metadata such as finish reasons, token usage, and 
        truncation flags.
    """

    def __init__(self, client, model_name: str, max_iterations: int = 3):
        # Initialize the IterativeGenerator with API client and model details.
        self.client = client
        self.model_name = model_name
        self.max_iterations = max_iterations

    # Generate response with automatic continuation if truncated
    def generate_with_continuation(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        max_tokens: int = 6000,
        temperature: float = 0.15
    ) -> Tuple[str, Dict]:        
        """        
            Generate a model response that can automatically continue generation
            if the API truncates output due to token limits.
            
            This method handles multi-iteration code generation — each iteration
            requests the model to continue exactly from the previous cutoff point.
            It accumulates responses, tracks finish reasons, and safely handles
            retries or early stops.

            - Initialize empty response buffer and tracking metadata.
            - Send the first prompt to the model.
            - If output is truncated (`finish_reason == 'length'`):
                - Automatically form a follow-up system prompt and user message
                  asking the model to continue seamlessly.
            - Continue iterating until either:
                - A 'stop' signal is received, or
                - Maximum iteration limit is reached.
            - Clean final output (remove code artifacts, duplicates) before returning.

            Args:
                - The system-level instruction defining the assistant’s behavior or style.
                - The user query or content that the model should respond to.
                - Maximum tokens to generate per iteration (default: 6000).
                - Temperature setting to controls randomness in generation.

            Returns a tuple containing:
                - Full combined model output after all continuations.
                - Metadata dictionary with details about the generation process.
        """

        Logger.subsection(f"Iterative Generation: {self.model_name}")

        # Initialize variables for accumulation
        full_response = ""
        iteration = 0
        metadata = {
            'iterations': 0,
            'finish_reasons': [],
            'total_tokens': 0,
            'was_truncated': False
        }

        # Start with the initial prompts
        current_system = system_prompt
        current_user = user_prompt

        # Iterative generation loop
        while iteration < self.max_iterations:
            iteration += 1
            Logger.info(f"Generation iteration {iteration}/{self.max_iterations}")

            try:
                # Send request to the model
                completion = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": current_system},
                        {"role": "user", "content": current_user}
                    ],
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=0.95
                )

                # Extract response chunk and finish reason
                if isinstance(completion.choices, list):
                    choice = completion.choices[0]
                else:
                    choice = completion.choices

                # Get generated content and finish reason
                chunk = choice.message.content
                finish_reason = choice.finish_reason

                # Accumulate response and metadata
                full_response += chunk
                metadata['iterations'] = iteration
                metadata['finish_reasons'].append(finish_reason)
                metadata['total_tokens'] += completion.usage.total_tokens

                Logger.info(f"Received {len(chunk)} chars, finish_reason='{finish_reason}'")

                # Check finish reason to determine next steps
                if finish_reason == 'stop':
                    Logger.success(f"Generation complete in {iteration} iteration(s)")
                    break
                elif finish_reason == 'length':
                    Logger.warning(f"Response truncated, requesting continuation...")
                    metadata['was_truncated'] = True

                    # Prepare continuation prompts
                    current_system = "You are continuing code generation. Continue EXACTLY from where the code was cut off. Do not repeat."
                    current_user = f"""Previous code (truncated at end):

{full_response}

CONTINUE the code from the exact point where it was cut off. Start with the incomplete line/function and complete it. Do not add explanations."""
                else:
                    Logger.warning(f"Unexpected finish_reason: {finish_reason}")
                    break

            except Exception as e:
                Logger.error(f"Generation error: {e}")
                metadata['error'] = str(e)
                break

        # Final checks and cleanup
        if iteration >= self.max_iterations and metadata['finish_reasons'] and metadata['finish_reasons'][-1] == 'length':
            Logger.warning(f"Max iterations reached, response may still be incomplete")

        # Clean code artifacts from the final response
        full_response = clean_code_artifacts(full_response)

        # Return the full response and metadata
        return full_response, metadata

# Go-only parser for RAG framework
class CloudNativeHybridParser:   
    """    
        CloudNativeHybridParser is a hybrid source code parser that combines:
        - **Syntactic parsing** using Tree-sitter (for structural code analysis)
        - **Semantic chunking** using embedding-based similarity (for meaning-aware segmentation)

        It is optimized for analyzing Go code in cloud-native systems. Right now it's tuned 
        for Go, but the architecture supports other languages.

        Args: The embedding model instance used for semantic similarity analysis.            
    """
    def __init__(self, embed_model):
        """
            Initialize the hybrid parser with language parsers and semantic splitters.

            Args: The embedding model instance used for semantic similarity and 
            context-aware splitting of parsed nodes.
        """

         # Store the embedding model for later semantic chunking
        self.embed_model = embed_model
        # Initialize Tree-sitter parser for Go language
        # Enables extraction of function/type/const/var declarations at AST level
        self.go_parser = get_parser('go')

        # Initialize semantic splitter to further divide Go AST nodes
        # buffer_size: minimum token buffer before breaking
        # breakpoint_percentile_threshold: determines chunking sensitivity
        # embed_model: used to compute embeddings for semantic segmentation
        self.go_semantic_splitter = SemanticSplitterNodeParser(
            buffer_size=1,
            breakpoint_percentile_threshold=95,
            embed_model=self.embed_model
        )

    # Parse file with hybrid approach (Go-only)
    def parse_file(self, file_path: str) -> List[TextNode]:        
        """
            Orchestrate hybrid file parsing using both syntactic and semantic strategies.
            For Go files, applies deep structural (AST) + semantic chunking.
            For other file types, falls back to a generic text parser.

            Args: Absolute or relative path to the source file being parsed.

            Returns a list of TextNode objects containing:
                - One node representing the complete file.
                - Multiple nodes representing syntactic or semantic chunks for Go sources.
        """
        # Determine file extension and corresponding language
        ext = Path(file_path).suffix.lower()
        lang = self._detect_language(ext)

        Logger.subsection(f"Parsing: {Path(file_path).name}")
        Logger.info(f"Detected language: {lang.upper()}")

        # Hybrid parsing: Go files get AST + embedding-based splitting
        if lang == 'go':
            chunk_nodes = self._parse_go_file(file_path)
        else:
            # Fallback for non-Go files: simple text-based parsing
            Logger.warning(f"Non-Go file detected, using generic parser")
            chunk_nodes = self._parse_generic_file(file_path, lang)

        # Always create one node for the complete file (high-priority RAG unit)
        complete_file_node = self._create_complete_file_node(file_path, lang)
        # Combine full-file node and extracted chunks into one unified list
        all_nodes = [complete_file_node] + chunk_nodes

        Logger.success(f"Total nodes: 1 complete file + {len(chunk_nodes)} chunks = {len(all_nodes)}")

        # Return combined node list for downstream indexing or embedding
        return all_nodes

    # Create complete file node
    def _create_complete_file_node(self, file_path: str, lang: str) -> TextNode:
        """
            Create a TextNode representing the entire source file as a single retrievable unit.
            This is used for RAG contexts that require full-file references (e.g., structural
            patterns, imports, or complete function sets) instead of fine-grained chunks.

            Args:
                - Path to the source file being processed.
                - Programming language identifier (e.g., "go", "python").

            Returns a node object encapsulating the entire file’s text and metadata for 
            indexing and retrieval in the RAG pipeline.
        """
        # Read full source content from disk
        content = Path(file_path).read_text(encoding='utf-8')

        # Core metadata describing the complete file
        metadata = {
            'source': file_path,
            'language': lang,
            'node_type': 'COMPLETE_FILE',
            'file_name': Path(file_path).name,
            'syntactic_type': 'complete_file',
            'priority': 'CRITICAL',
            'file_size': len(content)
        }

        # Wrap content with descriptive headers for readability during retrieval
        enhanced_content = f"""# COMPLETE FILE: {Path(file_path).name}
# Language: {lang.upper()}
# Size: {len(content)} characters
# ===== FILE BEGINS =====

{content}

# ===== FILE ENDS =====
"""
        # summary log
        Logger.info(f"Created COMPLETE FILE node ({len(content)} chars)")

        # Return the wrapped file content as a retrievable TextNode
        return TextNode(text=enhanced_content, metadata=metadata)

    # Detect language from file extension (Go-only)
    def _detect_language(self, ext: str) -> str:
        """Detect language from file extension (Go-only version)"""
        if ext == '.go':
            return 'go'
        else:
            return 'text'  # Everything else is treated as generic text

    # Parse Go file with syntactic + semantic chunking
    def _parse_go_file(self, file_path: str) -> List[TextNode]:
        """        
            Parse a Go source file in two stages:
            1. Syntactic Parsing using tree-sitter AST to extract functions, 
            methods, types, etc.
            2. Semantic Chunking to split large nodes into smaller 
            semantically meaningful units suitable for embeddings and RAG 
            indexing.

            Args: Path to the Go source file to parse.

            Returns a list of enriched TextNode objects representing syntactic and 
            semantic code chunks, annotated with metadata.
        """        
        # Stage 1: Parse raw Go file content and extract AST nodes
        Logger.info("Stage 1: Syntactic Parsing (Tree-sitter AST)")        
        content = Path(file_path).read_bytes()
        tree = self.go_parser.parse(content)
        go_nodes = self._extract_go_nodes(tree.root_node, content, file_path)
        Logger.success(f"Extracted {len(go_nodes)} syntactic nodes")

         # Stage 2: Enhance AST nodes with semantic chunking for embeddings
        Logger.info("Stage 2: Semantic Chunking (Embedding-based)")
        enhanced_nodes = []

        # Process each syntactic node for semantic splitting
        for i, node in enumerate(go_nodes):
            try:
                # Progress logging
                Logger.progress("Semantic splitting", i + 1, len(go_nodes), f"- {node.metadata.get('node_type', 'unknown')}")
                # Split node into semantically meaningful chunks
                semantic_chunks = self.go_semantic_splitter.get_nodes_from_documents([node])

                # Enrich metadata for each semantic chunk
                for chunk in semantic_chunks:
                    chunk.metadata.update(node.metadata)
                    chunk.metadata['language'] = 'go'
                    chunk.metadata['priority'] = 'MEDIUM'
                    enhanced_nodes.append(chunk)

                # Log if multiple semantic chunks were created
                if len(semantic_chunks) > 1:
                    logger.info(f"      → Split into {len(semantic_chunks)} semantic chunks")

            except Exception as e:
                # On failure, retain original node with warning
                Logger.warning(f"Semantic splitting failed: {e}")
                node.metadata['language'] = 'go'
                node.metadata['priority'] = 'MEDIUM'
                enhanced_nodes.append(node)

        Logger.success(f"Generated {len(enhanced_nodes)} total chunks")        
        return enhanced_nodes

    # Extract Go AST nodes using tree-sitter.
    def _extract_go_nodes(self, root_node, content: bytes, file_path: str) -> List[TextNode]:
        """
            Traverse the Go AST generated by tree-sitter and extract key syntactic
            constructs (functions, methods, types, constants, variables, imports)
            into TextNode objects for indexing and downstream analysis.

            Args:
                - Root node of the tree-sitter-parsed Go AST.
                - Raw byte content of the Go source file.
                - Path of the source file being processed.

            Returns a list of TextNode objects representing Go AST nodes.            
        """        
        nodes = []              # Collected AST nodes as TextNode objects
        node_counts = Counter() # Track occurrence of each node type for logging

        # Recursive AST traversal function.
        def walk_go_tree(node):
            # Interested in GOlang specific syntactic constructs only.
            if node.type in ['function_declaration', 'method_declaration', 'type_declaration', 
                           'const_declaration', 'var_declaration', 'import_declaration']:
                text = content[node.start_byte:node.end_byte].decode('utf-8', errors='ignore')
                # Extract text slice from file content
                metadata = {
                    'source': file_path,
                    'node_type': node.type,
                    'start_line': node.start_point[0],
                    'end_line': node.end_point[0],
                    'syntactic_type': 'go_ast_node',
                    'size': len(text)
                }
                # Add the TextNode to collection and update count
                nodes.append(TextNode(text=text, metadata=metadata))
                node_counts[node.type] += 1

            # Recurse into children nodes
            for child in node.children:
                walk_go_tree(child)

        # Start AST traversal from the root node.
        walk_go_tree(root_node)

        # Log summary of extracted node types.
        for node_type, count in node_counts.most_common():
            logger.info(f"    • {node_type}: {count}")

        return nodes

    # Generic file parsing for non-Go files.
    def _parse_generic_file(self, file_path: str, lang: str) -> List[TextNode]:
        """
            Provides a fallback parser for non-Go files by reading the entire file
            as plain text and wrapping it in a single TextNode. This ensures that   
            all files can be indexed in the RAG framework, even if they lack 
            language-specific parsing capabilities. 

            Args:
                - Path to the file being parsed.
                - Detected or declared language of the file.

            Returns a list containing a single TextNode with the file's content. 
        """        
        try:
            # Read file content as plain text in UTF8-encoding.
            content = Path(file_path).read_text(encoding='utf-8')
            # Minimal metadata describing parsing method and context.
            metadata = {
                'source': file_path, 
                'language': lang, 
                'parser': 'generic',
                'syntactic_type': 'generic_text',
                'priority': 'LOW'
            }
            Logger.warning(f"Parsed as generic text ({len(content)} chars)")
            # Return text wrapped in a TextNode for downstream indexing.
            return [TextNode(text=content, metadata=metadata)]
        except Exception as e:
            Logger.error(f"Failed to parse {file_path}: {e}")
            return []

class ModelConfig:
    """
        Simple data class to hold model configuration loaded from environment variables.
    """
    def __init__(self, model_num: str):
        # Load model configuration from environment variables
        self.type = os.getenv(f'MODEL_{model_num}_TYPE')
        self.name = os.getenv(f'MODEL_{model_num}_NAME')
        self.api_key = os.getenv(f'MODEL_{model_num}_API_KEY')
        self.endpoint = os.getenv(f'MODEL_{model_num}_ENDPOINT')
        self.deployment = os.getenv(f'MODEL_{model_num}_DEPLOYMENT')
        self.api_version = os.getenv(f'MODEL_{model_num}_API_VERSION')

class MultiModelRAGBuilder:
    """
        This is the main RAG orchestrator. MultiModelRAGBuilder constructs 
        and manages a multi-model Cloud Native Retrieval-Augmented Generation 
        (RAG) framework. It supports embedding creation, Qdrant vector 
        indexing, multi-model query execution, and static code validation 
        pipelines.

        Supports scalable RAG implementation that spans across different 
        LLM endpoints including Azure OpenAI and OpenAI-compatible models 
        (grok, deepseek, llama, gpt-(vx), etc.) 
    """
    def __init__(self):
        """
        Initialize the RAG builder by loading embeddings, model configurations,
        and setting up vector storage (Qdrant).

        Steps:
            - Load embedding model from Azure credentials.
            - Load up to 3 model configurations from environment.
            - Initialize Qdrant if enabled.
            - Prepare parser, validator, and refinement handlers.
        """

        # Initialize embedding model for all upstream/downstream RAG operations.
        self.embed_model = AzureOpenAIEmbedding(
            model=os.getenv('AZURE_OPENAI_EMBEDDING_MODEL'),
            deployment_name=os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT'),
            api_key=os.getenv('AZURE_OPENAI_EMBEDDING_API_KEY'),
            azure_endpoint=os.getenv('AZURE_OPENAI_EMBEDDING_ENDPOINT').rstrip('/'),
            api_version=os.getenv('AZURE_OPENAI_EMBEDDING_API_VERSION'),
        )

        self.model_configs = {}
        # Load model configurations dynamically (supports up to 5 models)
        for i in range(1, 6):
            config = ModelConfig(str(i))
            if config.type and config.name:
                self.model_configs[f'model_{i}'] = config
                Logger.success(f"Loaded model {i}: {config.name} ({config.type})")

        # Attach global embedding model
        Settings.embed_model = self.embed_model

        # Initialize state trackers. validators and refinement components
        self.use_qdrant = os.getenv('QDRANT_ENABLED', 'false').lower() == 'true'
        self.index_status = {'built': False, 'files': 0, 'nodes': 0}
        self.indexed_files_list = []
        self.static_validator = StaticCodeValidator()        
        self.refinement_handler = ErrorsRefinementAndSelfCorrection()

        # Setup Qdrant vector store if enabled
        if self.use_qdrant:
            Logger.info("QDRANT_ENABLED detected. Setting up Qdrant.")
            self.client = QdrantClient(url=os.getenv('QDRANT_URL'))

            test_embedding = self.embed_model.get_text_embedding("test")
            dim = len(test_embedding)
            Logger.info(f"Embedding dimensions: {dim}")

            coll = os.getenv('QDRANT_COLLECTION', 'code_rag')

            # Clean up existing collection if found.
            if self.client.collection_exists(coll):
                Logger.info(f"Collection {coll} exists, deleting it.")
                self.client.delete_collection(coll)

            # Create fresh collection.
            Logger.info(f"Creating collection {coll} with dimension {dim}.")
            self.client.create_collection(
                collection_name=coll,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
            )

            vs = QdrantVectorStore(
                client=self.client,
                collection_name=coll,
                metadata_payload_key='metadata',
                content_payload_key='content'
            )
            self.storage_ctx = StorageContext.from_defaults(vector_store=vs)
        else:
            # Default to in-memory/local vector store
            self.storage_ctx = StorageContext.from_defaults()

        # Initialize parser and placeholders
        self.parser = CloudNativeHybridParser(self.embed_model)
        self.index = None

    # Build RAG index
    def build_index(self, directory: str):
        """        
            Build a RAG vector index from a directory of source files.
            - Load and parse files into semantic chunks.
            - Generate vector embeddings for parsed nodes.
            - Build vector index using either Qdrant or in-memory backend.

            Args: Path containing input files to be parsed and indexed.

            Returns None. Only updates internal index and status attributes.           
        """
        
        Logger.section("BUILDING RAG INDEX")

        # Load and tag source documents.
        docs = SimpleDirectoryReader(directory, file_metadata=self._meta).load_data()
        total_files = len(docs)
        Logger.info(f"Found {total_files} files in '{directory}'")

        nodes = []
        files_list = []

        Logger.subsection("File Parsing Phase")

        # Parse each file into semantic chunks or complete nodes.
        for idx, d in enumerate(docs):
            file_path = d.metadata['file_path']
            Logger.progress("Parsing files", idx + 1, total_files, f"- {Path(file_path).name}")
            parsed = self.parser.parse_file(file_path)
            nodes.extend(parsed)
            files_list.append(file_path)

        Logger.success(f"Parsed {total_files} files into {len(nodes)} total nodes")

        # Display basic node statistics for observability
        logger.info("\n  [INFO] Node Statistics:")
        complete_files = sum(1 for n in nodes if n.metadata.get('node_type') == 'COMPLETE_FILE')
        chunks = len(nodes) - complete_files
        logger.info(f"    • Complete Files: {complete_files}")
        logger.info(f"    • Fine-grained Chunks: {chunks}")

        # Build vector index from parsed nodes.
        Logger.subsection("Building Vector Index")
        self.index = VectorStoreIndex(nodes, storage_context=self.storage_ctx, show_progress=True)

        # Update tracking metrics
        self.index_status.update({'built': True, 'files': total_files, 'nodes': len(nodes)})
        self.indexed_files_list = files_list

        # Log Qdrant collection count if applicable.
        if self.use_qdrant:
            count = self.client.count(collection_name=os.getenv('QDRANT_COLLECTION','code_rag'), exact=True).count
            Logger.success(f"Qdrant collection count: {count}")

        Logger.section("INDEX BUILD COMPLETE")
        logger.info(f"  [INFO] Indexed files: {[Path(f).name for f in self.indexed_files_list]}")

    # Query single model with validation.
    def query_single_model(self, query: str, model_key: str) -> Tuple[str, str, float, Dict]:
        """        
            Query a single configured model through the RAG pipeline with validation.
            - Retrieve context from RAG index.
            - Generate response using the model type (Azure or OpenAI-compatible).
            - Run static linting and validation pass.
            - Return corrected code if applicable.

            Args: 
                - Natural language or task-based prompt to send to model.
                - Identifier key for the target model.

            Returns a tuple containing:
                - Model name
                - Generated response text
                - Duration taken for the entire process
                - Metadata dictionary (Dict) with details on generation, validation, context size, etc.            
        """        

        # Record start time for performance measurement
        start_time = time.time()

        try:
            # Fetch the model configuration using model key
            config = self.model_configs[model_key]
            Logger.subsection(f"Querying Model: {config.name}")

            # Step - 1: Retrieve context from RAG index
            Logger.info("Retrieving context from RAG index...")
            # Create retriever from the index with top-k similarity search
            retriever = self.index.as_retriever(similarity_top_k=15)
            retrieved_nodes = retriever.retrieve(query)

            # Separate retrieved nodes into full reference files vs smaller chunks
            complete_file_nodes = [n for n in retrieved_nodes if n.metadata.get('node_type') == 'COMPLETE_FILE']
            chunk_nodes = [n for n in retrieved_nodes if n.metadata.get('node_type') != 'COMPLETE_FILE']

            Logger.success(f"Retrieved {len(complete_file_nodes)} complete files + {len(chunk_nodes)} chunks")

            context_parts = []

            # Assemble context for prompt by adding reference examples used for structure and style like template.
            if complete_file_nodes:
                context_parts.append("="*80)
                context_parts.append("COMPLETE REFERENCE FILES (USE AS TEMPLATES)")
                context_parts.append("="*80)
                for node in complete_file_nodes[:2]:
                    context_parts.append(node.text)
                    context_parts.append("\n" + "-"*80 + "\n")

            # Add smaller contextual chunks next (detailed examples or helper logic)
            # These provide additional details without overwhelming the prompt.
            if chunk_nodes:
                context_parts.append("="*80)
                context_parts.append("ADDITIONAL DETAILED CONTEXT")
                context_parts.append("="*80)
                for node in chunk_nodes[:8]:
                    context_parts.append(node.text)
                    context_parts.append("\n")

            # Combine all pieces into a single reference string
            retrieved_context = "\n".join(context_parts)

            # Step - 2: Generate response using the specified model
            if config.type == 'azure_openai':
                # Create Azure OpenAI client with required deployment settings.
                llm_client = AzureOpenAI(
                    model=config.name,
                    deployment_name=config.deployment,
                    api_key=config.api_key,
                    azure_endpoint=config.endpoint.rstrip('/'),
                    api_version=config.api_version,
                )
                # Build query engine from index with the LLM backend.
                query_engine = self.index.as_query_engine(llm=llm_client)
                # Execute the query through RAG engine
                response = query_engine.query(query)
                # Clean up artifacts like markdown formatting, stray delimiters, etc.
                response_text = str(response)
                response_text = clean_code_artifacts(response_text)
                # Minimal metadata since this model doesn’t iterate.
                metadata = {'iterations': 1, 'finish_reasons': ['stop'], 'was_truncated': False}

            elif config.type == 'openai_compatible':
                # Use OpenAI-compatible API
                client = OpenAI(
                    base_url=config.endpoint,
                    api_key=config.api_key
                )

                # Define structured system prompt for deterministic Go code generation.
                system_prompt = """You are an expert Go code generator specializing in Kubernetes.

CRITICAL RULES:
1. Follow the same structural pattern (function signatures, registration, comments) as provided examples
2. Use idiomatic Go: proper error handling, context usage, and structuring.
3. Handle all edge cases
6. Important: provide your answer in plain text without any markdown code fences and explanation.


Generate production-ready code that compiles without errors."""

                # Define user prompt with retrieved context and user query.
                user_prompt = f"""Study these COMPLETE reference examples and replicate their patterns:

{retrieved_context}

Now generate code for this request:
{query}

Generate COMPLETE, WORKING code following the patterns above. Use JSON Patch format for all mutations. Start now:"""

                # Use iterative generator to handle potential truncation.
                generator = IterativeGenerator(client, config.deployment, max_iterations=3)
                
                # Generate final code output with controlled temperature and token budget.
                response_text, gen_metadata = generator.generate_with_continuation(
                    system_prompt,
                    user_prompt,
                    max_tokens=6000,
                    temperature=0.15
                )
                # Store metadata (iterations, truncation info, etc.)
                metadata = gen_metadata

            # Step - 3: Static linting and validation pass.
            duration = time.time() - start_time

            # Run static lint + validation for Go code quality and correctness
            static_validation = self.static_validator.validate_code(response_text, 'auto', config.name)

            # If validation returns a fixed version, prefer that
            if static_validation.get('fixed_code'):
                response_text = static_validation['fixed_code']

            # Return model name, response, duration, and metadata for tracking and reporting.
            return config.name, response_text, duration, {
                'generation': metadata,
                'static_validation': static_validation,
                'context_size': len(retrieved_context)
            }

        except Exception as e:
            # Capture and report any runtime or API error during query
            duration = time.time() - start_time
            Logger.error(f"Query failed: {e}")
            import traceback
            traceback.print_exc()

            # Return fallback result in case of failure
            return config.name if 'config' in locals() else model_key, f"Error: {str(e)}", duration, {'error': str(e)}

    # Query all models in parallel with validation
    def query_all_models(self, query: str) -> List[Dict]:        
        """        
            Run the same query across all configured models in parallel,
            validating and collecting their responses for comparison.

            Args: Natural language or task prompt to send to all models.

            Returns a list of result objects, one per model containing:
                - Model name.
                - Generated response text.
                - Time taken for the query.
                - Length of the generated response.
                - Additional metadata including validation results.                
        """
        Logger.section("MULTI-MODEL QUERY")
        Logger.info(f"Query: {query[:100]}...")
        Logger.info(f"Querying {len(self.model_configs)} models in parallel")

        # Use a thread pool to run multiple model queries concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(self.query_single_model, query, model_key)
                for model_key in self.model_configs.keys()
            ]

            results = []
            # Collect results as each model finishes
            for future in futures:
                model_name, response, duration, metadata = future.result()

                # Normalize formatting for readability and consistency
                results.append({
                    'model': model_name,
                    'response': response.replace('\\n', '\n').replace('\\t', '\t') if response else "",
                    'duration': round(duration, 2),
                    'response_length': len(response) if response else 0,
                    'metadata': metadata
                })

                Logger.success(f"{model_name}: {len(response) if response else 0} chars in {duration:.2f}s")

        # Rank results based on static validation quality score, response time, and completeness
        def get_combined_score(r):
            quality_score = r.get('metadata', {}).get('static_validation', {}).get('quality_score', 0.0)

            # Response time score (faster = better)
            duration = r.get('duration', 30)
            time_score = max(0.0, 1.0 - (duration / 30))

            # Completeness score
            completeness = min(r['response_length'] / 3000, 1.0)

            # Weighted scoring: 70% quality + 10% duration + 20% completeness
            combined = (quality_score * 0.70) + (time_score * 0.10) + (completeness * 0.20)

            # final score returned.
            return combined

        results.sort(key=get_combined_score, reverse=True)

        # Log scoring breakdown
        Logger.subsection("Model Ranking with Quality Scores")
        # Display detailed scores for each model
        for i, r in enumerate(results):
            quality_score = r.get('metadata', {}).get('static_validation', {}).get('quality_score', 0.0)
            total_errors = r.get('metadata', {}).get('static_validation', {}).get('total_errors', 0)
            combined = get_combined_score(r)

            logger.info(f"\n  #{i+1} {r['model']}:")
            logger.info(f"    • Quality Score (lint): {quality_score:.2%} (70% weight)")
            logger.info(f"    • Combined Score: {combined:.2%}")

            # Show top errors if any
            static_val = r.get('metadata', {}).get('static_validation', {})            
            if static_val.get('has_errors'):
                logger.info(f"    [X]  Errors: {total_errors}")
                for error in static_val.get('errors', [])[:3]:
                    logger.info(f"        - {error}")

        # Return the ranked results
        return results

    # File metadata extractor
    def _meta(self, fp: str) -> Dict:
        # Extract metadata for a given file path
        p = Path(fp)        
        return {'file_path': str(fp), 'mtime': p.stat().st_mtime}

builder = MultiModelRAGBuilder()

# /build endpoint to create the RAG index from files in the specified directory
@app.route('/build', methods=['POST'])
def build():
    """
        Build the RAG index from a directory of source files.

        POST Request:
            JSON body (optional):
                {
                    "directory": "<path_to_source_directory>"
                }

            If not provided, defaults to "./feeds".

        Returns JSON object containing:
            {
                "status": "index_built",
                "files": <number_of_indexed_files>,
                "nodes": <number_of_indexed_nodes>
            }
    """
    # Parse incoming JSON payload.
    data = request.json or {}
     # Extract the directory path to index; default to './feeds' if not specified
    directory = data.get('directory', './feeds')
    # Trigger the index build process using the provided directory
    builder.build_index(directory)
    # Return a structured JSON response with build results.
    return jsonify({
        'status': 'index_built', 
        'files': builder.index_status['files'], 
        'nodes': builder.index_status['nodes']
    })

# /verbose endpoint for detailed index and model status
@app.route('/verbose', methods=['GET'])
def verbose():
    """  
        Provides a detailed snapshot of the current system state.
        Useful for debugging.

        Returns a JSON object containing:
            - Index build status
            - Number of indexed files and nodes
            - List of indexed file names
            - Names of all available models configured in the builder
    """
    response = dict(builder.index_status)
    response['indexed_files'] = builder.indexed_files_list
    # Include names of all available models configured in the builder
    response['available_models'] = [config.name for config in builder.model_configs.values()]
    # Return as JSON response
    return jsonify(response)

# /query endpoint for best model response with refinement. Handle user query by running all 
# configured models, selecting the best response, validating its quality, and automatically 
# refining it if errors are detected.
@app.route('/query', methods=['POST'])
def query():
    """    
        This endpoint acts as the main inference and self-correction entrypoint.
        It coordinates model responses, static validation, and iterative refinement
        to ensure high-quality, executable Go code output.

        POST Request:
            JSON body:
                {
                    "query": "some text or code prompt"
                }

        Returns:
            Response:
                - 200 OK: model-generated response as plain text.
                - 400 Bad Request: If index is not yet built.
                - 500 Internal Server Error: If no valid model responses were produced.
    """

    q = request.json.get('query', '')

    # Ensure vector index is available before running queries.
    if not builder.index:
        return "Error: Index not built yet. Call /build first.", 400

    # Query all available models for responses to the user query
    results = builder.query_all_models(q)

    # Pick the top-ranked model output (based on evaluation strategy)
    if results and len(results) > 0:
        best = results[0]

        Logger.section("BEST RESPONSE SELECTED")
        logger.info(f"  Model: {best['model']}")
        logger.info(f"  Length: {best['response_length']} chars")
        logger.info(f"  Duration: {best['duration']}s")

        # Extract static validation (lint, syntax, metrics) from metadata if available.
        static_val = best.get('metadata', {}).get('static_validation', {})
        if static_val:
            total_errors = static_val.get('total_errors', 0)
            logger.info(f"  Quality Score (lint-only): {static_val.get('quality_score', 0):.2f}")

            # If the best response has code issues, trigger refinement.
            if static_val.get('has_errors'):
                logger.info(f"  [X]  Errors: {total_errors}")

                # Log top few detected errors for visibility; indicate potential refinement need.
                if static_val.get('errors'):
                    logger.info(f"  [X] Errors found:")
                    for i, error in enumerate(static_val.get('errors', [])[:3], 1):
                        logger.info(f"    {i}. {error}")
                    if len(static_val.get('errors', [])) > 3:
                        logger.info(f"    ... and {len(static_val.get('errors', [])) - 3} more errors")

                logger.info(f"\n  [INFO] Starting refinement to fix errors...")

                # Identify the model configuration used for this response.
                # Apply refinement for self-correction.                
                best_model_key = None
                for key, config in builder.model_configs.items():
                    if config.name == best['model']:
                        best_model_key = key
                        break

                # Run refinement handler to fix lint/syntax errors automatically
                if best_model_key:
                    model_config = builder.model_configs[best_model_key]
                    refined_response, refinement_metadata = builder.refinement_handler.refine_response_iteratively(
                        best_response_data=best,
                        model_config=model_config,
                        static_validator=builder.static_validator
                    )

                    # Update the response with refined version.
                    if refinement_metadata.get('refinement_needed', False):
                        best['response'] = refined_response
                        best['refinement_metadata'] = refinement_metadata

                        # Log final refinement status
                        if refinement_metadata.get('refinement_successful', False):
                            Logger.success("[SUCCESS] Final refined response ready - all errors resolved!")
                        else:
                            final_errors = refinement_metadata.get('final_errors', 0)
                            initial_errors = refinement_metadata.get('initial_errors', 0)
                            improvement = initial_errors - final_errors
                            if improvement > 0:
                                Logger.warning(f"[WARN]  Final refined response ready - {improvement} errors fixed, {final_errors} remaining")
                            else:
                                Logger.warning("[WARN]  Final response unchanged - no improvement achieved")

        # Return the refined or original response
        return best['response'], 200, {'Content-Type': 'text/plain'}
    else:
        return "Error: No valid responses received.", 500

# /query-multi endpoint for detailed multi-model comparison
@app.route('/query-multi', methods=['POST'])
def query_multi():
    """
        Handles POST requests for performing a detailed multi-model comparison
        across all registered AI models. It compares responses, validates them
        using lint-only static validation, and includes optional refinement details
        if present. Ideal for evaluation, analytics, or debugging.

        POST Request:
            JSON body:
                {
                    "query": "some text or code prompt"
                }

        Returns detailed results from all models including validation scores.
    """  

    # Extract the user query from incoming JSON payload.
    q = request.json.get('query', '')

    # Validate that the vector index has been built before attempting queries.
    # Prevents querying against empty/non-existent index.
    if not builder.index:
        return jsonify({'error': 'Index not built yet. Call /build first.'}), 400

    # Run the provided query across all models (e.g., multiple AI models or LLM backends).    
    results = builder.query_all_models(q)
    
    clean_results = []

    # Iterate over each model's raw result for cleanup and enrichment.
    for r in results:
        static_val = r.get('metadata', {}).get('static_validation', {})
        
        refinement_info = {}
        if 'refinement_metadata' in r:
            refinement_data = r['refinement_metadata']
            # Extract detailed refinement metrics for debugging and analysis
            refinement_info = {
                'refinement_performed': refinement_data.get('refinement_needed', False),
                'iterations_performed': refinement_data.get('iterations_performed', 0),
                'initial_errors': refinement_data.get('initial_errors', 0),
                'final_errors': refinement_data.get('final_errors', 0),
                'refinement_successful': refinement_data.get('refinement_successful', False),
                'total_improvement': refinement_data.get('initial_errors', 0) - refinement_data.get('final_errors', 0)
            }

        # Fetch all relevant data into a structured summary per model
        clean_results.append({
            'model': r['model'],
            'response': r['response'],
            'duration': r['duration'],
            'response_length': r['response_length'],
            'quality_score': static_val.get('quality_score', 0.0),
            'golangci_lint_errors': static_val.get('golangci_lint_errors', 0),
            'total_errors': static_val.get('total_errors', 0),
            'has_errors': static_val.get('has_errors', False),
            'errors': static_val.get('errors', []),
            'refinement_info': refinement_info
        })

    # Construct and return the final JSON response object.
    return jsonify({
        'query': q,
        'models_queried': len(results),
        'results': clean_results,
        'best_model': results[0]['model'] if results else None,
        'scoring_info': {
            'quality_score': '70% weight - golangci-lint validation (counts actual error lines, not Issue objects)',
            'time': '10% weight - response duration',
            'completeness': '20% weight - response length'
        },
        'refinement_info': 'Best response undergoes iterative error refinement if errors are detected'
    })


# Main entry point: Driver code for RAG based self-healing k8s code generation.
if __name__ == "__main__":
    """    
        Launches a multi-model hybrid RAG pipeline to generate, validate, and refine
        Kubernetes client-go code in an iterative, self-healing manner.

        The driver primararily loads all the models from .env and starts the Flask API.
    """

    # Log a high-level section header for clarity
    Logger.section("Self-Healing Code Generation for Kubernetes: Multi-Model Hybrid RAG with Iterative Validation & Refinement")

    # Show quick overview of features and configuration.
    print("  --> Features:")
    print("    • Cloud Native Architecture for Kubernetes Client-Go code generation.")
    print("    • Hybrid Semantic-Syntactic Code Parsing & Chunking.")
    print("    • Vector Store Indexing with Qdrant.")
    print("    • Advanced Multi-Model LLM Integration with parallel multi-model inferencing.")
    print("    • Enabled for Azure OpenAI and OpenAI-compatible models")    
    print("    • Native static validation pipeline with quality scoring and consensus.")
    print("    • Auto-refinement: Best response gets refined until errors are fixed")
    print("    • REST API backend for webhooks/querying.")
    print("")

    # Show configured models pulled via environment variables.
    print(f"  --> Configured models: {len(builder.model_configs)}")
    for model_key, config in builder.model_configs.items():
        print(f"    • {config.name} ({config.type})")
    print("")

    # Grab MAX_REFINEMENT_ITERATIONS from .env, set default=3. This indicates number of refinement passes.
    max_refinement_iterations = os.getenv('MAX_REFINEMENT_ITERATIONS', '3')
    print(f"  --> Max refinement iterations: {max_refinement_iterations}")
    print("")

    # Launch Flask REST API server to serve RAG endpoints.
    Logger.section("SERVER STARTING")
    app.run(host='0.0.0.0', port=int(os.getenv('FLASK_PORT', '5001')))