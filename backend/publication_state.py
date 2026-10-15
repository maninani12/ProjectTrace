"""Bounded ORM cache and shared JSON working state for private correlation."""
from collections import OrderedDict

from backend.db import Record


class FindingView:
    def __init__(self, owner, identity):
        self.owner, self.id = owner, identity

    @property
    def data(self):
        return self.owner.data[self.id]

    @data.setter
    def data(self, value):
        self.owner.data[self.id] = value
        context = self.owner.db.info.get("analysis_generation")
        if context is None:
            raise ValueError("Private correlation requires a generation owner.")
        context.finding_updates[self.id] = value
        if len(context.finding_updates) >= 250:
            context.batch()


class FindingRecords:
    def __init__(self, db, snapshots=(), maximum=250):
        self.db, self.maximum = db, maximum
        self.data, self.cache = {}, OrderedDict()
        old_ids = []
        for snapshot in snapshots:
            if isinstance(snapshot, str):
                old_ids.append(snapshot)
            else:
                self.data[snapshot["id"]] = snapshot["data"]
        # Compatibility with earlier encrypted v1 receipts containing IDs only.
        if old_ids:
            from sqlalchemy import select

            from backend.generation_models import GenerationRecord
            context = db.info.get("analysis_generation")
            if not context:
                raise ValueError("Legacy finding context requires its private generation.")
            for offset in range(0, len(old_ids), 250):
                expected = old_ids[offset:offset + 250]
                rows = db.execute(select(Record.__table__.c.id, Record.__table__.c.data).join(
                    GenerationRecord.__table__, GenerationRecord.record_id == Record.id).where(
                    GenerationRecord.generation_id == context.generation_id, Record.id.in_(expected)))
                actual = {row.id: row.data for row in rows}
                if set(actual) != set(expected):
                    raise ValueError("Legacy finding context is unavailable in scope.")
                self.data.update(actual)

    def __setitem__(self, identity, record):
        if identity != record.id:
            raise ValueError("Finding working-set identity is inconsistent.")
        self.data[identity] = record.data
        self.cache[identity] = record
        self.cache.move_to_end(identity)
        while len(self.cache) > self.maximum:
            old_id, old_record = self.cache.popitem(last=False)
            self.data[old_id] = old_record.data

    def __getitem__(self, identity):
        if identity not in self.data:
            raise KeyError(identity)
        record = self.cache.get(identity)
        if record is not None:
            self.cache.move_to_end(identity)
            return record
        return FindingView(self, identity)

    def snapshots(self):
        for identity, record in self.cache.items():
            self.data[identity] = record.data
        return [{"id": identity, "data": data} for identity, data in self.data.items()]
