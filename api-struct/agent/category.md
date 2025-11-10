AI Risk Categorization Logic
Overview
This document outlines the logic for automatically categorizing AI systems based on user responses 

Categorization Rules
Rule 1: Prohibited AI
If ANY question in the "Prohibited AI Use Assessment" section is answered "Yes" (and relevant follow-up questions confirm prohibition), categorize as:

PROHIBITED AI

Rule 2: High-Risk AI
If ALL questions in the "Prohibited AI Use Assessment" section are answered "No" or cleared through follow-up questions, BUT at least ONE question in the "High-Risk AI Assessment" section is answered "Yes", categorize as:

HIGH-RISK AI

Rule 3: Low-Risk AI
If ALL questions in BOTH the "Prohibited AI Use Assessment" and "High-Risk AI Assessment" sections are answered "No", categorize as:

LOW-RISK AI

Implementation Notes
First check all Prohibited AI questions (questions 1-7 in the assessment)

For multi-part questions, check the follow-up responses to confirm prohibition
If any prohibited use is confirmed, immediately categorize as PROHIBITED AI
If no prohibited uses are found, check all High-Risk AI questions (questions 1-8 in the high-risk section)

If any high-risk question is answered "Yes", categorize as HIGH-RISK AI
If neither prohibited nor high-risk conditions are met, categorize as LOW-RISK AI

The operational context questions (region of operation) do not affect the risk categorization but should be stored for compliance purposes

Error Handling and Validation
Missing Data: If any critical question responses are missing, flag for manual review rather than making an automatic categorization

Inconsistent Answers: If follow-up question answers contradict parent questions, flag for manual review

Maybe/Uncertain Responses: For questions with "Maybe" responses in prohibited categories, consider escalating for human review

Verification Step: Include a confidence score with the categorization, and recommend human verification for scores below a threshold

Audit Trail: Maintain a record of which specific questions triggered the categorization for future reference and explanation

Example Decision Flow
Read all responses from DynamoDB table
Validate data completeness
Apply Rule 1 → If triggered, return "PROHIBITED AI"
Apply Rule 2 → If triggered, return "HIGH-RISK AI"
Apply Rule 3 → If triggered, return "LOW-RISK AI"
If any validation issues are found, flag for manual review