"""Cron utility module with command sanitization for FemtoBot."""
import subprocess
import shutil
import re
import logging
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class CronError(Exception):
    """Raised when there's an error with cron operations."""
    pass


class CronUtils:
    """Utilities for managing system crontab with security validation."""
    
    # Dangerous characters/patterns that could lead to command injection
    DANGEROUS_PATTERNS = [
        r';\s*rm\s',  # rm after semicolon
        r';\s*sudo\s',  # sudo after semicolon
        r'\|\s*bash(?:\s|$)',  # pipe to bash
        r'\|\s*sh(?:\s|$)',  # pipe to sh
        r'`[^`]+`',  # command substitution with backticks
        r'\$\((?!date\s+\+)[^)]+\)',  # command substitution with $(), except $(date +...)
        r'>\s*/etc/',  # writing to /etc
        r'>\s*/bin/',  # writing to /bin
        r'>\s*/usr/bin/',  # writing to /usr/bin
        r'&&\s*rm\s',  # rm with AND
        r'wget\s+.*\|',  # wget piped to shell
        r'curl\s+.*\|',  # curl piped to shell
    ]
    
    # Allowed characters in cron schedule (numbers, spaces, commas, dashes, slashes, asterisks)
    SCHEDULE_PATTERN = re.compile(r'^[\d\s,\-\*/]+$')
    
    @staticmethod
    def _validate_schedule(schedule: str) -> bool:
        """
        Validates cron schedule format (5 fields: min hour day month dow).
        
        Args:
            schedule: Cron schedule string
            
        Returns:
            True if valid, False otherwise
        """
        parts = schedule.split()
        if len(parts) != 5:
            logger.warning(f"Invalid schedule format: expected 5 fields, got {len(parts)}")
            return False
        
        for part in parts:
            if not CronUtils.SCHEDULE_PATTERN.match(part):
                logger.warning(f"Invalid schedule field: {part}")
                return False
        
        return True
    
    @staticmethod
    def _is_schedule_in_future(schedule: str) -> tuple[bool, str]:
        """
        Check if a one-time cron schedule is in the future.
        
        Args:
            schedule: Cron schedule string (5 fields)
            
        Returns:
            Tuple of (is_future, error_message)
        """
        parts = schedule.split()
        if len(parts) != 5:
            return False, "Invalid schedule format"
        
        # Check if this looks like a one-time job (specific numbers, not wildcards)
        try:
            minute = int(parts[0])
            hour = int(parts[1])
            day = int(parts[2])
            month = int(parts[3])
            
            # Only validate one-time jobs (specific dates, not wildcards)
            if parts[0] != '*' and parts[1] != '*' and parts[2] != '*' and parts[3] != '*':
                from datetime import datetime
                now = datetime.now()
                scheduled_time = datetime(now.year, month, day, hour, minute)
                
                # If scheduled time is in the past, reject it
                if scheduled_time < now:
                    return False, f"Cannot schedule job in the past: {scheduled_time.strftime('%H:%M %d/%m/%Y')}"
        except (ValueError, IndexError):
            # Not a one-time job or parsing error, skip validation
            pass
        
        return True, ""
    
    @staticmethod
    def _sanitize_command(command: str) -> tuple[bool, str]:
        """
        Sanitizes and validates a command for security.
        
        Args:
            command: Command string to validate
            
        Returns:
            Tuple of (is_safe, error_message)
        """
        if not command or not command.strip():
            return False, "Command cannot be empty"
        
        # Check for dangerous patterns BEFORE stripping to preserve trailing spaces
        for pattern in CronUtils.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                logger.warning(f"Dangerous pattern detected in command: {pattern}")
                return False, f"Command contains dangerous pattern: {pattern}"
        
        command = command.strip()
        
        # Check for multiple commands (potential injection)
        if ';' in command and not (command.startswith('echo') or command.startswith('notify-send') or command.startswith('[')):
            # Allow semicolons only in specific safe contexts
            logger.warning(f"Multiple commands detected (semicolon)")
            return False, "Multiple commands not allowed for security"
        
        # Check for shell escapes
        if command.count('`') % 2 != 0:
            return False, "Unmatched backticks detected"
        
        return True, ""
    
    @staticmethod
    def get_crontab() -> List[str]:
        """
        Returns the current crontab content as a list of lines.
        
        Returns:
            List of cron job lines
        """
        try:
            result = subprocess.run(
                ['crontab', '-l'], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            if result.returncode != 0:
                # crontab might be empty/no crontab for user
                return []
            return [line for line in result.stdout.strip().split('\n') if line.strip()]
        except FileNotFoundError:
            logger.error("crontab command not found")
            return []
        except Exception as e:
            logger.error(f"Error reading crontab: {e}")
            return []

    @staticmethod
    def add_job(schedule: str, command: str) -> bool:
        """
        Adds a new job to the crontab with validation.
        
        Args:
            schedule: Cron schedule (5 fields: min hour day month dow)
            command: Command to execute
            
        Returns:
            True if successful, False otherwise
        """
        # Validate schedule
        if not CronUtils._validate_schedule(schedule):
            logger.error(f"Invalid cron schedule: {schedule}")
            return False
        
        # Check if schedule is in the future (for one-time jobs)
        is_future, error_msg = CronUtils._is_schedule_in_future(schedule)
        if not is_future:
            logger.error(f"Schedule validation failed: {error_msg}")
            return False
        
        # Validate and sanitize command
        is_safe, error_msg = CronUtils._sanitize_command(command)
        if not is_safe:
            logger.error(f"Command rejected: {error_msg}")
            return False
        
        current_jobs = CronUtils.get_crontab()
        new_job = f"{schedule} {command}"
        
        # Avoid duplicates
        if new_job in current_jobs:
            logger.info(f"Cron job already exists: {new_job[:60]}...")
            return True
        
        # Check for similar jobs (same schedule, similar command)
        for job in current_jobs:
            job_parts = job.split(None, 5)  # Split into 6 parts: 5 schedule + command
            if len(job_parts) >= 6:
                existing_schedule = ' '.join(job_parts[:5])
                if existing_schedule == schedule:
                    logger.warning(f"Job with same schedule already exists: {job[:60]}...")
        
        current_jobs.append(new_job)
        
        success = CronUtils._write_crontab(current_jobs)
        if success:
            logger.info(f"Added cron job: {new_job[:60]}...")
        return success

    @staticmethod
    def delete_job(substring: str) -> bool:
        """
        Deletes jobs that contain the substring.
        
        Args:
            substring: Text to search for in jobs
            
        Returns:
            True if any jobs were deleted, False otherwise
        """
        if not substring or not substring.strip():
            logger.warning("Empty substring provided for delete_job")
            return False
        
        current_jobs = CronUtils.get_crontab()
        new_jobs = [job for job in current_jobs if substring not in job]
        
        if len(new_jobs) == len(current_jobs):
            logger.info(f"No jobs found matching: {substring}")
            return False
        
        removed_count = len(current_jobs) - len(new_jobs)
        success = CronUtils._write_crontab(new_jobs)
        if success:
            logger.info(f"Removed {removed_count} cron job(s) matching: {substring}")
        return success

    @staticmethod
    def _write_crontab(jobs: List[str]) -> bool:
        """
        Helper to write list of jobs to crontab.
        
        Args:
            jobs: List of cron job lines
            
        Returns:
            True if successful, False otherwise
        """
        if not shutil.which('crontab'):
            logger.error("crontab command not available")
            return False
        
        # Ensure each job ends with exactly one newline
        new_content = '\n'.join(jobs)
        if new_content:
            new_content += '\n'
        
        try:
            process = subprocess.Popen(
                ['crontab', '-'], 
                stdin=subprocess.PIPE, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            stdout, stderr = process.communicate(input=new_content)
            
            if process.returncode != 0:
                logger.error(f"Error saving crontab: {stderr}")
                return False
            
            logger.debug("Crontab updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Exception saving crontab: {e}", exc_info=True)
            return False

    @staticmethod
    def cleanup_old_jobs() -> int:
        r"""
        Removes one-time cron jobs that have already passed.
        Handles:
        1. Explicit year guards: [ "$(date +\%Y)" = "2026" ]
        2. Implicit one-time jobs: specific min/hour/day/month (no wildcards)
        """
        current_jobs = CronUtils.get_crontab()
        now = datetime.now()
        current_year = now.year
        jobs_to_keep = []
        removed_count = 0
        
        for job in current_jobs:
            if not job.strip():
                continue
            
            parts = job.split()
            if len(parts) < 5:
                jobs_to_keep.append(job)
                continue
                
            # --- 1. explicit year guard ---
            # Try matching [ "$(date +%Y)" = "YYYY" ] OR [ "$(date +\%Y)" = "YYYY" ]
            # Using raw string r'' for regex reliability
            year_match = re.search(r'\[ "\$\(date \\?\+%Y\)" = "(\d{4})" \]', job)
            
            if year_match:
                try:
                    target_year = int(year_match.group(1))
                    if parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit() and parts[3].isdigit():
                        minute, hour, day, month = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                        job_time = datetime(target_year, month, day, hour, minute)
                        
                        if job_time < now:
                            removed_count += 1
                            logger.info(f"[CLEANUP] Removing expired (explicit): {job[:60]}...")
                            continue # Don't keep this job
                except (ValueError, IndexError):
                    logger.warning(f"Could not parse explicit date in cron: {job[:60]}...")

            # --- 2. implicit one-time job ---
            # If day and month are specific numbers, assume it's for CURRENT year unless proven otherwise.
            # Only consider if no year guard was parsed/matched already (or matched and kept)
            # Actually, if year_match passed but job kept, it means it's future.
            # The issue is jobs WITHOUT year guard like "Comprar papa"
            elif not year_match:
                # Check for: INT INT INT INT * ...
                if (parts[0].isdigit() and parts[1].isdigit() and 
                    parts[2].isdigit() and parts[3].isdigit() and 
                    parts[4] == '*'):
                    try:
                        minute, hour, day, month = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                        # Assume current year
                        job_time = datetime(current_year, month, day, hour, minute)
                        
                        # If passed, remove
                        if job_time < now:
                            removed_count += 1
                            logger.info(f"[CLEANUP] Removing expired (implicit): {job[:60]}...")
                            continue
                    except (ValueError, IndexError):
                        pass

            jobs_to_keep.append(job)
        
        if removed_count > 0:
            success = CronUtils._write_crontab(jobs_to_keep)
            if success:
                logger.info(f"Cleaned up {removed_count} old cron job(s)")
            else:
                logger.error("Failed to write crontab during cleanup")
        
        return removed_count
    
    @staticmethod
    def validate_existing_jobs() -> List[str]:
        """
        Validates all existing cron jobs and returns warnings for suspicious entries.
        
        Returns:
            List of warning messages
        """
        warnings = []
        jobs = CronUtils.get_crontab()
        
        for i, job in enumerate(jobs, 1):
            if not job.strip():
                continue
            
            parts = job.split(None, 5)
            if len(parts) < 6:
                warnings.append(f"Line {i}: Incomplete job (missing schedule or command)")
                continue
            
            command = parts[5]
            is_safe, error_msg = CronUtils._sanitize_command(command)
            if not is_safe:
                warnings.append(f"Line {i}: Suspicious command - {error_msg}")
        
        return warnings
