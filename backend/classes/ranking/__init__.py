"""Ranking engines for the classroom rebuild (BUSINESS-ARCHITECTURE §3).

Two independent systems that never share inputs:
  - sat:   SAT performance only (TestAttempt scaled scores)
  - academic: graded work × completion (SubmissionReview / AssessmentResult / attendance)
"""
