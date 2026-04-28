"""
Email templates for deactivated interns notifications.
"""

def get_deactivation_email(intern_name: str, stage_number: int = None, feedback: str = None):
    """
    Generate a professional deactivation notification email.
    
    Args:
        intern_name: Name of the intern
        stage_number: Which stage they were deactivated at (optional)
        feedback: Specific feedback about why they didn't advance (optional)
    
    Returns:
        dict with 'subject' and 'body' keys
    """
    
    stage_mention = f" at Stage {stage_number}" if stage_number else ""
    feedback_section = f"\n\n**Feedback:**\n{feedback}" if feedback else ""
    
    subject = "HNG 14 Internship: Did Not Progress - Next Steps"
    
    body = f"""Dear {intern_name},

Thank you for your participation in the HNG 14 Internship Program. After careful review of your performance, we regret to inform you that you were not selected to advance in the internship program{stage_mention}.

**What This Means:**
- You will no longer have access to the HNG 14 workspace and channels
- Your internship participation has been concluded for this cohort
- You will not receive further updates or communications related to this cohort

**Why This Happened:**
We evaluate interns based on task completion, code quality, communication, and collaboration. While you showed promise, the current performance metrics indicated that additional time would be needed before you're ready for the next stage.{feedback_section}

**Next Steps:**
We encourage you not to be discouraged! Many successful professionals have faced setbacks. Here's what we recommend:

1. **Review Feedback**: Take time to understand areas for improvement
2. **Continue Learning**: Build your skills through online courses, projects, and practice
3. **Reapply**: When the next cohort opens, we'd love to see you apply again with strengthened skills
4. **Stay Connected**: Follow HNG on social media for updates on future opportunities

**Reapplication Information:**
- Next cohort applications will open: [Date TBA]
- Visit: https://hng.tech for more details
- Feel free to reach out if you have questions about the program

We appreciate your effort and wish you the best in your development journey. Keep coding, keep learning, and we hope to see you in a future cohort!

Best regards,
HNG Team
---
HNG Internship Program
https://hng.tech
"""
    
    return {
        'subject': subject,
        'body': body
    }


def get_batch_summary_template(count: int, emails_sent: list, emails_failed: list = None):
    """
    Generate a summary of batch email sending operation.
    
    Args:
        count: Total number of emails processed
        emails_sent: List of successfully sent email addresses
        emails_failed: List of failed email addresses (optional)
    
    Returns:
        str with summary information
    """
    
    failed_count = len(emails_failed) if emails_failed else 0
    success_count = len(emails_sent)
    
    summary = f"""
📧 DEACTIVATION EMAIL BATCH SUMMARY
{'='*50}
Total Processed: {count}
✅ Successfully Sent: {success_count}
❌ Failed: {failed_count}

SENT TO:
{chr(10).join(f'  ✓ {email}' for email in emails_sent)}
"""
    
    if emails_failed:
        summary += f"""
FAILED:
{chr(10).join(f'  ✗ {email}' for email in emails_failed)}
"""
    
    return summary


# Template for testing/dry-run
DEACTIVATION_EMAIL_TEST = """
This is a TEST/DRY-RUN email preview:

TO: [intern_email@example.com]
SUBJECT: HNG 14 Internship: Did Not Progress - Next Steps

Dear [Intern Name],

Thank you for your participation in the HNG 14 Internship Program...

[Full email content would be displayed here during dry-run]
"""
