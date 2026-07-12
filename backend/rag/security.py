import re 
import trace
from typing import Optional
from langsmith import traceable

class InputSanitizer:

    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"forget\s+(all\s+)?previous",
        r"new\s+instructions\s*:",
        r"system\s*prompt",
        r"---\s*end\s*(of)?\s*prompt",
        r"pretend\s+you\s+are",
        r"act\s+as\s+(if\s+)?you",
        r"bypass\s+(all\s+)?restrictions",
        r"reveal\s+(your|the)\s+(system|instructions|prompt)",
        r"you\s+are\s+now\s+(DAN|jailbroken)",
    ]

    def __init__(self):
        self.patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.INJECTION_PATTERNS
        ]

    def check(self, text: str) -> tuple[bool, Optional[str]]:
        for pattern in self.patterns: # Check for potentially dangerous delimiters
            if pattern.search(text):
                return False, "Blocked: potential prompt injection detected"
        return True, None
       
    def clean(self, text: str) -> str:  # Remove potentially dangerous delimiters from input
        text = re.sub(r'[-]{3,}', '', text)
        text = re.sub(r'[=]{3,}', '', text)
        text = text.replace('{{', '{ {').replace('}}', ' } }')
        return text.strip()
    
    def check_input(self, text: str) -> tuple[bool, str, Optional[str]]:
        is_allowed, reason = self.check(text)
        if not is_allowed:
            return False, "", reason
        cleaned_message = self.clean(text)
        return True, cleaned_message, "Input is safe"
    
class OutputValidator:
    HARMFUL_PATTERNS = [
        re.compile(r"here('s| is) (how|the way) to (hack|steal|attack)", re.I),
        re.compile(r"password\s+is\s+", re.I),
        re.compile(r"api[_\s]?key\s[:=]", re.I)
    ]

    def validate(self, output: str) -> tuple[str, list[str]]:
        warnings = []
        for pattern in self.HARMFUL_PATTERNS:
            if pattern.search(output):
                output = "[Response blocked: potentially harmful content]"
                warnings.append("Harmful content blocked")
                break
        return output, warnings

class SecurityPipeline:

    def __init__(self):
        self.sanitizer = InputSanitizer()
        self.output_validator = OutputValidator()

    @traceable(name="security_check_input")
    def check_input(self, text: str) -> tuple[bool, str, list[str]]:
        notes = []
        is_safe, reason = self.sanitizer.check(text)
        if not is_safe:
            return False, "", [reason]
        cleaned = self.sanitizer.clean(text)
        return True, cleaned, notes
    
    @traceable(name="security_check_output")
    def check_output(self, text: str) -> tuple[str, list[str]]:
        return self.output_validator.validate(text)