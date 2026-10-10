"""Real PostgreSQL administration qualification in disposable UUID schemas."""
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from backend import main
from backend.db import Base
from tests.test_administration_api import body, register
from tests.test_postgresql_integration import postgres  # noqa: F401 -- reuse explicitly scoped fixture


def test_postgresql_scoped_admin_commands_and_json_aggregates(postgres,monkeypatch):  # noqa: F811 -- imported fixture injection
    engine,factory=postgres
    Base.metadata.create_all(engine)
    monkeypatch.setattr(main,"Session",factory)
    main.rate_windows.clear()
    with TestClient(main.app) as client:
        client.headers['origin']='http://127.0.0.1:5173'
        identity=register(client,'postgres-owner@example.test','PostgreSQL administration')
        payload=body(name='PostgreSQL team')
        created=client.post('/api/admin/teams',json=payload)
        assert created.status_code==200,created.text
        assert client.post('/api/admin/teams',json=payload).json()['replayed']
        stale=client.post('/api/admin/teams/'+created.json()['id'],json=body(action='RENAME',name='Stale team',expected_version=0))
        assert stale.status_code==409
        from backend.domain import add
        with factory() as db:
            add(db,identity['organization_id'],None,'job',{'state':'COMPLETED','user_id':identity['access']['user_id'],'duration_ms':42})
            db.commit()
        for path in ('dashboard','jobs','usage','usage/actors','activity','audit','security','teams','users'):
            response=client.get('/api/admin/'+path)
            assert response.status_code==200,(path,response.text)
        assert client.get('/api/admin/usage').json()['total_recorded_duration_ms']==42
        assert client.get('/api/admin/activity').json()['page']['total']>=2
        target=created.json()['id']
        def rename(i):
            return client.post('/api/admin/teams/'+target,json=body(action='RENAME',name=f'Concurrent team {i}',expected_version=1)).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(rename,range(2)))==[200,409]
        event=client.get('/api/admin/activity?action=TEAM_RENAME').json()['items'][0]
        assert client.get('/api/admin/activity/'+event['id']).status_code==200
        with TestClient(main.app) as outsider:
            outsider.headers['origin']='http://127.0.0.1:5173'
            register(outsider,'postgres-other@example.test','Other PostgreSQL organization')
            assert outsider.get('/api/admin/teams/'+target).status_code==404
            assert outsider.get('/api/admin/activity/'+event['id']).status_code==404
            assert outsider.get('/api/admin/activity?action=TEAM_RENAME').json()['items']==[]
