"""The three pluggable adapter axes (canonical schemas sit in the middle):

- intake/        AXIS 3 — channels they use to generate leads     -> Lead
- inventory/     AXIS 1 — how they maintain their website         -> Vehicle
- organization/  AXIS 2 — how they organize/track their leads     -> consumes LeadEvent

Adding support for a new client process = one adapter file on the relevant axis, zero core changes.
"""
