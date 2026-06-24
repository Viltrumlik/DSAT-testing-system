# assessments domain services
#
# GOVERNANCE ARCHITECTURE:
#   All business logic for the immutable academic-record platform lives here.
#   Never scatter governance logic across views, serializers, or model.save().
#
# MODULES:
#   snapshot_builder.py     — deterministic, self-sufficient snapshot generation
#   snapshot_compat.py      — schema versioning and compatibility registry
#   publish_service.py      — transactional DRAFT → PUBLISHED orchestration
#   publish_validator.py    — full governance validation pipeline
#   governance_events.py    — immutable append-only event dispatch
#
# USAGE:
#   from assessments.domain.publish_service import publish_assessment_set
#   from assessments.domain.governance_events import emit_governance_event
#   from assessments.domain.publish_validator import validate_for_publish
