import csv
from cStringIO import StringIO
import datetime
import os

from pyramid.decorator import reify
from pyramid.events import NewResponse
from pyramid.events import subscriber
from pyramid.renderers import get_renderer
from pyramid.response import FileResponse
from pyramid.response import Response
from pyramid.view import view_config
from sqlalchemy.sql.expression import text

from ichnaea.db import Measure
from ichnaea.db import Score
from ichnaea.db import User


HERE = os.path.dirname(__file__)
FAVICON_PATH = os.path.join(HERE, 'static', 'favicon.ico')

MEASURE_HISTOGRAM_MYSQL = """\
select date(time) as day, count(id) as num from measure where
date_sub(curdate(), interval 30 day) <= time and
date(time) <= curdate() group by date(time)"""

MEASURE_HISTOGRAM_SQLITE = """\
select date(time) as day, count(id) as num from measure where
date('now', '-30 days') <= date(time) and
date(time) <= date('now') group by date(time)"""


def configure_content(config):
    config.add_view(favicon_view, name='favicon.ico',
                    http_cache=(86400, {'public': True}))
    config.add_view(robotstxt_view, name='robots.txt',
                    http_cache=(86400, {'public': True}))
    config.add_static_view(
        name='static', path='ichnaea.content:static', cache_max_age=3600)
    config.scan('ichnaea.content.views')


@subscriber(NewResponse)
def sts_header(event):
    response = event.response
    if response.content_type == 'text/html':
        response.headers.add('Strict-Transport-Security', 'max-age=2592000')


class Layout(object):

    @reify
    def base_template(self):
        renderer = get_renderer("templates/base.pt")
        return renderer.implementation().macros['layout']

    @reify
    def base_macros(self):
        renderer = get_renderer("templates/base_macros.pt")
        return renderer.implementation().macros


class ContentViews(Layout):

    def __init__(self, request):
        self.request = request

    @view_config(renderer='templates/homepage.pt', http_cache=300)
    def homepage_view(self):
        return {'page_title': 'Overview'}

    @view_config(renderer='string', name="map.csv", http_cache=300)
    def map_csv(self):
        session = self.request.database.session()
        select = text("select distinct round(lat / 100000) as lat, "
                      "round(lon / 100000) as lon from measure order by lat, lon")
        result = session.execute(select)
        rows = StringIO()
        csvwriter = csv.writer(rows)
        csvwriter.writerow(('lat', 'lon'))
        for lat, lon in result.fetchall():
            csvwriter.writerow((int(lat) / 100.0, int(lon) / 100.0))
        return rows.getvalue()

    @view_config(renderer='templates/map.pt', name="map", http_cache=300)
    def map_view(self):
        return {'page_title': 'Coverage Map'}

    @view_config(renderer='json', name="stats.json", http_cache=300)
    def stats_json(self):
        session = self.request.database.session()
        if 'sqlite' in str(session.bind.engine.url):
            query = MEASURE_HISTOGRAM_SQLITE
        else:  # pragma: no cover
            query = MEASURE_HISTOGRAM_MYSQL
        rows = session.execute(text(query))
        result = {'histogram': []}
        for day, num in rows.fetchall():
            if isinstance(day, datetime.date):  # pragma: no cover
                day = day.strftime('%Y-%m-%d')
            result['histogram'].append({'day': day, 'num': num})
        return result

    @view_config(renderer='templates/stats.pt', name="stats", http_cache=300)
    def stats_view(self):
        session = self.request.database.session()
        result = {'leaders': [], 'page_title': 'Statistics'}
        result['total_measures'] = session.query(Measure).count()

        score_rows = session.query(Score).order_by(Score.value.desc()).all()
        user_rows = session.query(User).all()
        users = {}
        for user in user_rows:
            users[user.id] = (user.token, user.nickname)

        for score in score_rows:
            token, nickname = users.get(score.id, ('', 'anonymous'))
            result['leaders'].append(
                {'token': token[:8], 'nickname': nickname, 'num': score.value})
        return result


def favicon_view(request):
    return FileResponse(FAVICON_PATH, request=request)


_robots_response = Response(content_type='text/plain',
                            body="User-agent: *\nDisallow: /\n")


def robotstxt_view(context, request):
    return _robots_response