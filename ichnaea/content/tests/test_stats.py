# -*- coding: utf-8 -*-
from calendar import timegm
from datetime import date, timedelta
from mobile_codes import _countries

from ichnaea.models.content import (
    Score,
    ScoreKey,
    User,
    Stat,
    StatKey,
)
from ichnaea.content.stats import (
    countries,
    global_stats,
    histogram,
    leaders,
    leaders_weekly,
    transliterate,
)
from ichnaea.models import (
    Cell,
    Radio,
)
from ichnaea.tests.base import DBTestCase, TestCase
from ichnaea import util


def unixtime(value):
    return timegm(value.timetuple()) * 1000


class TestStats(DBTestCase):

    def test_global_stats(self):
        session = self.session
        day = util.utcnow().date() - timedelta(1)
        stats = [
            Stat(key=StatKey.cell, time=day, value=6100000),
            Stat(key=StatKey.wifi, time=day, value=3212000),
            Stat(key=StatKey.unique_cell, time=day, value=3289900),
            Stat(key=StatKey.unique_ocid_cell, time=day, value=1523000),
            Stat(key=StatKey.unique_wifi, time=day, value=2009000),
        ]
        session.add_all(stats)
        session.commit()

        result = global_stats(session)
        self.assertDictEqual(
            result, {
                'cell': '6.10', 'unique_cell': '3.28',
                'wifi': '3.21', 'unique_wifi': '2.00',
                'unique_ocid_cell': '1.52',
            })

    def test_global_stats_missing_today(self):
        session = self.session
        day = util.utcnow().date() - timedelta(1)
        yesterday = day - timedelta(days=1)
        stats = [
            Stat(key=StatKey.cell, time=yesterday, value=5000000),
            Stat(key=StatKey.cell, time=day, value=6000000),
            Stat(key=StatKey.wifi, time=day, value=3000000),
            Stat(key=StatKey.unique_cell, time=yesterday, value=4000000),
        ]
        session.add_all(stats)
        session.commit()

        result = global_stats(session)
        self.assertDictEqual(
            result, {
                'cell': '6.00', 'unique_cell': '4.00',
                'wifi': '3.00', 'unique_wifi': '0.00',
                'unique_ocid_cell': '0.00',
            })

    def test_histogram(self):
        session = self.session
        today = util.utcnow().date()
        one_day = today - timedelta(days=1)
        two_days = today - timedelta(days=2)
        one_month = today - timedelta(days=35)
        two_months = today - timedelta(days=70)
        long_ago = today - timedelta(days=100)
        stats = [
            Stat(key=StatKey.cell, time=long_ago, value=40),
            Stat(key=StatKey.cell, time=two_months, value=50),
            Stat(key=StatKey.cell, time=one_month, value=60),
            Stat(key=StatKey.cell, time=two_days, value=70),
            Stat(key=StatKey.cell, time=one_day, value=80),
            Stat(key=StatKey.cell, time=today, value=90),
        ]
        session.add_all(stats)
        session.commit()
        result = histogram(session, StatKey.cell, days=90)
        self.assertTrue(
            [unixtime(one_day), 80] in result[0])

        if two_months.month == 12:
            expected = date(two_months.year + 1, 1, 1)
        else:
            expected = date(two_months.year, two_months.month + 1, 1)
        self.assertTrue(
            [unixtime(expected), 50] in result[0])

    def test_histogram_different_stat_name(self):
        session = self.session
        day = util.utcnow().date() - timedelta(days=1)
        stat = Stat(key=StatKey.unique_cell, time=day, value=9)
        session.add(stat)
        session.commit()
        result = histogram(session, StatKey.unique_cell)
        self.assertEqual(result, [[[unixtime(day), 9]]])

    def test_leaders(self):
        session = self.session
        today = util.utcnow().date()
        test_data = []
        for i in range(20):
            test_data.append((u'nick-%s' % i, 30))
        highest = u'nick-high-too-long_'
        highest += (128 - len(highest)) * u'x'
        test_data.append((highest, 40))
        lowest = u'nick-low'
        test_data.append((lowest, 20))
        for nick, value in test_data:
            user = User(nickname=nick)
            session.add(user)
            session.flush()
            score = Score(key=ScoreKey.location,
                          userid=user.id, time=today, value=value)
            session.add(score)
        session.commit()
        # check the result
        result = leaders(session)
        self.assertEqual(len(result), 22)
        self.assertEqual(result[0]['nickname'], highest[:24] + u'...')
        self.assertEqual(result[0]['num'], 40)
        self.assertTrue(lowest in [r['nickname'] for r in result])

    def test_leaders_weekly(self):
        session = self.session
        today = util.utcnow().date()
        test_data = []
        for i in range(1, 11):
            test_data.append((u'nick-%s' % i, i))
        for nick, value in test_data:
            user = User(nickname=nick)
            session.add(user)
            session.flush()
            score = Score(key=ScoreKey.new_cell,
                          userid=user.id, time=today, value=value)
            session.add(score)
            score = Score(key=ScoreKey.new_wifi,
                          userid=user.id, time=today, value=21 - value)
            session.add(score)
        session.commit()

        # check the result
        result = leaders_weekly(session, batch=5)
        self.assertEqual(len(result), 2)
        self.assertEqual(set(result.keys()), set(['new_cell', 'new_wifi']))

        # check the cell scores
        scores = result['new_cell']
        self.assertEqual(len(scores), 5)
        self.assertEqual(scores[0]['nickname'], 'nick-10')
        self.assertEqual(scores[0]['num'], 10)
        self.assertEqual(scores[-1]['nickname'], 'nick-6')
        self.assertEqual(scores[-1]['num'], 6)

        # check the wifi scores
        scores = result['new_wifi']
        self.assertEqual(len(scores), 5)
        self.assertEqual(scores[0]['nickname'], 'nick-1')
        self.assertEqual(scores[0]['num'], 20)
        self.assertEqual(scores[-1]['nickname'], 'nick-5')
        self.assertEqual(scores[-1]['num'], 16)

    def test_countries(self):
        session = self.session
        cell_key = {'lac': 1, 'cid': 1}
        test_data = [
            Cell(radio=Radio.gsm, mcc=1, mnc=1, **cell_key),
            Cell(radio=Radio.lte, mcc=262, mnc=1, **cell_key),
            Cell(radio=Radio.gsm, mcc=310, mnc=1, **cell_key),
            Cell(radio=Radio.gsm, mcc=310, mnc=2, **cell_key),
            Cell(radio=Radio.gsm, mcc=313, mnc=1, **cell_key),
            Cell(radio=Radio.cdma, mcc=310, mnc=1, **cell_key),
            Cell(radio=Radio.umts, mcc=244, mnc=1, **cell_key),
            Cell(radio=Radio.lte, mcc=244, mnc=1, **cell_key),
        ]
        session.add_all(test_data)
        session.commit()

        # check the result
        expected = set(['ALA', 'BMU', 'DEU', 'FIN', 'GUM', 'PRI', 'USA'])
        result = countries(session)
        self.assertEqual(len(result), len(expected))
        self.assertEqual(set([r['code'] for r in result]), expected)

        country_results = {}
        for r in result:
            code = r['code']
            country_results[code] = r
            del country_results[code]['code']
            del country_results[code]['name']

        # a simple case with a 1:1 mapping of mcc to ISO country code
        self.assertEqual(country_results['DEU'],
                         {'cdma': 0, 'gsm': 0, 'lte': 1, 'total': 1,
                          'umts': 0, 'multiple': False, 'order': 'germany'})

        # mcc 310 is valid for both GUM/USA, 313 only for USA
        self.assertEqual(country_results['USA'],
                         {'cdma': 1, 'gsm': 3, 'lte': 0, 'total': 4,
                          'umts': 0, 'multiple': True, 'order': 'united sta'})
        self.assertEqual(country_results['GUM'],
                         {'cdma': 1, 'gsm': 2, 'lte': 0, 'total': 3,
                          'umts': 0, 'multiple': True, 'order': 'guam'})

        # These two countries share a mcc, so we report the same data
        # for both of them
        self.assertEqual(country_results['FIN'],
                         {'cdma': 0, 'gsm': 0, 'lte': 1, 'total': 2,
                          'umts': 1, 'multiple': True, 'order': 'finland'})
        self.assertEqual(country_results['ALA'],
                         {'cdma': 0, 'gsm': 0, 'lte': 1, 'total': 2,
                          'umts': 1, 'multiple': True, 'order': 'aland isla'})


class TestTransliterate(TestCase):

    def test_countries(self):
        for country in _countries():
            trans = transliterate(country.name)
            non_ascii = [c for c in trans if ord(c) > 127]
            self.assertEqual(len(non_ascii), 0)
