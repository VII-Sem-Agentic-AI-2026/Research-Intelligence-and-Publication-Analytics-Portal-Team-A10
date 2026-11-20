import http.client
import json
import time
import unittest
import test_accounts_roles as fixtures
from publication_agent.accounts import Forbidden
from publication_agent.tunnel_access import validate_request,public_origin

class TunnelAccessTests(unittest.TestCase):
    setUp=fixtures.AccountsRolesTests.setUp
    tearDown=fixtures.AccountsRolesTests.tearDown
    request=fixtures.AccountsRolesTests.request
    login=fixtures.AccountsRolesTests.login

    def register(self,origin='https://synthetic-portal.trycloudflare.com',expires=None):
        (self.root/'cloudflare_origin.json').write_text(json.dumps({'origin':origin,'expires_at':expires if expires is not None else time.time()+300}),encoding='utf-8')

    def test_public_login_sets_secure_cookie_and_uses_existing_authentication(self):
        self.register()
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        client.request('POST','/api/login',json.dumps({'username':'asha','password':fixtures.PASSWORD}),{'Host':f'127.0.0.1:{self.server.server_port}','Origin':'https://synthetic-portal.trycloudflare.com','Content-Type':'application/json'})
        response=client.getresponse();response.read()
        self.assertEqual(response.status,200)
        cookie=response.getheader('Set-Cookie');self.assertIn('; Secure',cookie);self.assertIn('HttpOnly',cookie)
        client.close()
        self.assertEqual(self.request('/api/me',cookie=cookie.split(';')[0])[0],200)

    def test_only_exact_registered_origin_is_allowed(self):
        self.register()
        validate_request({'Host':'127.0.0.1:8001','Origin':'https://synthetic-portal.trycloudflare.com'},self.root)
        for origin in ['https://other.trycloudflare.com','https://evil.invalid','http://synthetic-portal.trycloudflare.com']:
            with self.assertRaises(Forbidden):validate_request({'Host':'127.0.0.1:8001','Origin':origin},self.root)
        with self.assertRaises(Forbidden):validate_request({'Host':'evil.invalid'},self.root)

    def test_registration_expires_and_local_origin_still_works(self):
        self.register(expires=time.time()-1)
        self.assertIsNone(public_origin(self.root))
        with self.assertRaises(Forbidden):validate_request({'Host':'127.0.0.1:8001','Origin':'https://synthetic-portal.trycloudflare.com'},self.root)
        validate_request({'Host':'127.0.0.1:8001','Origin':'http://127.0.0.1:8001'},self.root)

    def test_malformed_registration_does_not_allow_remote_origin(self):
        for value in ['http://x.trycloudflare.com','https://x.trycloudflare.com/','https://user@x.trycloudflare.com','https://x.trycloudflare.com.evil.invalid','https://x.trycloudflare.com:443']:
            self.register(value);self.assertIsNone(public_origin(self.root))
        (self.root/'cloudflare_origin.json').write_text('{',encoding='utf-8')
        self.assertIsNone(public_origin(self.root))

    def test_health_identifies_supported_portal_without_exposing_project_path(self):
        status,result,_=self.request('/api/health')
        self.assertEqual(status,200);self.assertTrue(result['tunnel_support'])
        self.assertEqual(result['service'],'research-portal');self.assertEqual(len(result['instance']),16)
        self.assertNotIn(str(self.root),json.dumps(result))
