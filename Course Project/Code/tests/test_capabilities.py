import unittest
from publication_agent.assistant import user_capabilities

class CapabilityTests(unittest.TestCase):
    def test_administrator_cannot_claim_academic_approval(self):
        text=' '.join(user_capabilities({'role':'admin'}))
        self.assertNotIn('Approve validated reports',text)
        self.assertIn('does not permit academic approval',text)

    def test_dean_can_review_and_approve_but_not_manage_accounts(self):
        text=' '.join(user_capabilities({'role':'dean'}))
        self.assertIn('Approve validated reports',text)
        self.assertIn('Inspect evidence',text)
        self.assertNotIn('Create and disable accounts',text)

    def test_faculty_can_generate_personal_reports_and_upload_own_exports(self):
        text=' '.join(user_capabilities({'role':'faculty'}))
        self.assertIn('your own records',text)
        self.assertIn('personal publication report',text)
        self.assertNotIn('Approve validated reports',text)
        self.assertNotIn('institutional research records',text)

    def test_hod_scope_is_explicit(self):
        self.assertIn('assigned department',' '.join(user_capabilities({'role':'hod'})))

if __name__=='__main__':unittest.main()
