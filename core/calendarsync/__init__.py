"""OAuth-backed calendar sync (plan §7c) -- Microsoft Graph and Google
Calendar, read-only. This package talks to the network and to OAuth
libraries, so it lives in core/, not engine/; the pure capacity math it
feeds lives in engine/calendar_capacity.py instead."""
