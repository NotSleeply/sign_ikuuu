import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

import sign_ikuuu as sign


def response(payload=None, url=sign.BASE_URL + '/user', status=200):
    result = requests.Response()
    result.status_code = status
    result.url = url
    result._content = json.dumps(payload).encode('utf-8')
    return result


class CheckinTests(unittest.TestCase):
    def test_bom_and_colon_in_password(self):
        self.assertEqual(
            sign.load_accounts('\ufeffa@example.test:pass:word\n\nb@example.test:second'),
            [('a@example.test', 'pass:word'), ('b@example.test', 'second')],
        )

    def test_malformed_account_is_not_silently_skipped(self):
        for value in (None, '', ' ', 'missing-separator', 'a@example.test:'):
            with self.subTest(value=value), self.assertRaises(sign.CheckinError):
                sign.load_accounts(value)

    def test_malformed_cookie_configuration_fails(self):
        for value in ('not-json', '[]', 'null'):
            with self.subTest(value=value), self.assertRaises(sign.CheckinError):
                sign.load_saved_cookies(value)

    def test_cookie_scope_and_expiry_are_preserved(self):
        cookies = [
            {'name': 'auth', 'value': 'valid', 'domain': '.ikuuu.top',
             'path': '/user', 'secure': True, 'expires': 4000000000},
            {'name': 'old', 'value': 'expired', 'domain': 'ikuuu.top', 'expires': 1},
        ]
        with sign.session_from_cookies(cookies) as session:
            auth = next(iter(session.cookies))
            self.assertEqual(len(session.cookies), 1)
            self.assertEqual((auth.domain, auth.path, auth.secure), ('.ikuuu.top', '/user', True))
            allowed = session.prepare_request(requests.Request('POST', sign.BASE_URL + '/user/checkin'))
            other = session.prepare_request(requests.Request('GET', 'https://example.test/user'))
            self.assertIn('auth=valid', allowed.headers['Cookie'])
            self.assertNotIn('Cookie', other.headers)

    def test_foreign_cookie_domain_is_rejected(self):
        with self.assertRaises(sign.CheckinError):
            sign.session_from_cookies([{'name': 'auth', 'value': 'value', 'domain': 'example.test'}])

    def test_expired_login_redirect_is_rejected(self):
        session = Mock()
        session.get.return_value = response(url=sign.BASE_URL + '/auth/login')
        with self.assertRaisesRegex(sign.CheckinError, '失效'):
            sign.verify_session(session)

    def test_checkin_outcomes(self):
        cases = [
            ({'ret': 1, 'msg': '获得流量'}, True),
            ({'ret': '1', 'msg': '获得流量'}, True),
            ({'ret': 0, 'msg': '您今天已经签到过了'}, True),
            ({'ret': 0, 'msg': '请先登录'}, False),
            ({'ret': -1, 'msg': '签到失败'}, False),
            ({'msg': '未知结果'}, False),
            ({'ret': 1}, False),
            ([], False),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                session = Mock()
                session.post.return_value = response(payload)
                if expected:
                    self.assertEqual(sign.submit_checkin(session), payload['msg'])
                else:
                    with self.assertRaises(sign.CheckinError):
                        sign.submit_checkin(session)

    def test_checkin_redirect_and_invalid_json_fail(self):
        redirected = response(status=302)
        redirected.headers['Location'] = '/auth/login'
        invalid_json = response()
        invalid_json._content = b'<html>login</html>'
        for result in (redirected, invalid_json, response(status=403)):
            with self.subTest(status=result.status_code):
                session = Mock()
                session.post.return_value = result
                with self.assertRaises((sign.CheckinError, requests.HTTPError)):
                    sign.submit_checkin(session)

    def test_saved_session_does_not_run_captcha_login(self):
        cookies = [{'name': 'auth', 'value': 'value'}]
        with patch.object(sign, 'playwright_login') as login, \
                patch.object(sign, 'verify_session'), \
                patch.object(sign, 'submit_checkin', return_value='签到成功'):
            success, _ = sign.checkin_one_account('a@example.test', 'password', cookies)
        self.assertTrue(success)
        login.assert_not_called()

    def test_failure_details_redact_credentials(self):
        with patch.object(sign, 'playwright_login', side_effect=RuntimeError('a@example.test secret-password')):
            success, message = sign.checkin_one_account('a@example.test', 'secret-password')
        self.assertFalse(success)
        self.assertNotIn('a@example.test', message)
        self.assertNotIn('secret-password', message)

    def test_all_accounts_are_attempted_after_failure(self):
        environment = {'ACCOUNTS': 'a@example.test:first\nb@example.test:second'}
        with patch.dict(os.environ, environment, clear=True), \
                patch.object(sign, 'checkin_one_account', side_effect=[(False, 'failed'), (True, 'ok')]) as checkin:
            self.assertFalse(sign.handler())
        self.assertEqual(checkin.call_count, 2)

    def test_missing_configuration_exits_with_failure(self):
        environment = {key: value for key, value in os.environ.items() if key not in ('ACCOUNTS', 'IKUUU_COOKIES')}
        result = subprocess.run(
            [sys.executable, str(Path(sign.__file__).resolve())],
            env=environment, capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(b'wxmsg', result.stderr)


if __name__ == '__main__':
    unittest.main()
