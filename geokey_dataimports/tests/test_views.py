"""All tests for views."""

import os
import json

from django.core.files import File
from django.core.urlresolvers import reverse
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.test import TestCase, RequestFactory
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.auth.models import AnonymousUser
from django.contrib.sites.shortcuts import get_current_site

from geokey import version
from geokey.core.tests.helpers import render_helpers
from geokey.users.tests.model_factories import UserFactory
from geokey.projects.tests.model_factories import ProjectFactory
from geokey.categories.tests.model_factories import (
    CategoryFactory,
    TextFieldFactory
)
from geokey.contributions.models import Observation

from .helpers import file_helpers
from .model_factories import DataImportFactory
from ..helpers.context_helpers import does_not_exist_msg
from ..models import DataImport, DataField, DataFeature
from ..forms import CategoryForm, DataImportForm
from ..views import (
    IndexPage,
    AllDataImportsPage,
    AddDataImportPage,
    SingleDataImportPage,
    DataImportCreateCategoryPage,
    DataImportAssignFieldsPage,
    DataImportAllDataFeaturesPage,
    RemoveDataImportPage
)


no_rights_to_access_msg = 'You are not member of the administrators group ' \
                          'of this project and therefore not allowed to ' \
                          'alter the settings of the project'


# ###########################
# TESTS FOR ADMIN PAGES
# ###########################

class IndexPageTest(TestCase):
    """Test index page."""

    def setUp(self):
        """Set up test."""
        self.request = HttpRequest()
        self.request.method = 'GET'
        self.view = IndexPage.as_view()
        self.filters = {
            'without-data-imports-only': 'Without data imports',
            'with-data-imports-only': 'With data imports'
        }

        self.user = UserFactory.create()

        self.project_1 = ProjectFactory.create(add_admins=[self.user])
        self.project_2 = ProjectFactory.create(add_admins=[self.user])
        self.project_3 = ProjectFactory.create(add_admins=[self.user])
        self.project_4 = ProjectFactory.create(add_contributors=[self.user])
        self.project_5 = ProjectFactory.create()
        DataImportFactory.create(project=self.project_2)
        DataImportFactory.create(project=self.project_4)

        di_to_delete = DataImportFactory.create(project=self.project_3)
        if os.path.isfile(di_to_delete.file.path):
            os.remove(di_to_delete.file.path)
        di_to_delete.delete()

        self.project_1.dataimports_count = 0  # none added
        self.project_2.dataimports_count = 1  # added
        self.project_3.dataimports_count = 0  # added but deleted
        self.project_4.dataimports_count = 1  # added

        setattr(self.request, 'session', 'session')
        messages = FallbackStorage(self.request)
        setattr(self.request, '_messages', messages)

    def tearDown(self):
        """Tear down test."""
        for dataimport in DataImport.objects.all():
            if dataimport.file:
                dataimport.file.delete()

    def test_get_with_anonymous(self):
        """
        Test GET with with anonymous.

        It should redirect to login page.
        """
        self.request.user = AnonymousUser()
        response = self.view(self.request)

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

    def test_get_with_user(self):
        """
        Test GET with with user.

        It should render the page with all projects, where user is an
        administrator.
        """
        projects = [self.project_1, self.project_2, self.project_3]

        self.request.user = self.user
        response = self.view(self.request).render()

        rendered = render_to_string(
            'di_index.html',
            {
                'PLATFORM_NAME': get_current_site(self.request).name,
                'GEOKEY_VERSION': version.get_version(),
                'user': self.request.user,
                'messages': get_messages(self.request),
                'filters': self.filters,
                'projects': projects
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_user_only_without_dataimports(self):
        """
        Test GET with with user, but only projects without data imports.

        It should render the page with all projects, where user is an
        administrator. Those projects must also not have data imports.
        """
        projects = [self.project_1, self.project_3]

        self.request.user = self.user
        self.request.GET['filter'] = 'without-data-imports-only'
        response = self.view(self.request).render()

        rendered = render_to_string(
            'di_index.html',
            {
                'PLATFORM_NAME': get_current_site(self.request).name,
                'GEOKEY_VERSION': version.get_version(),
                'user': self.request.user,
                'messages': get_messages(self.request),
                'filters': self.filters,
                'projects': projects,
                'request': {
                    'GET': {
                        'filter': self.request.GET.get('filter')
                    }
                }
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_user_only_with_dataimports(self):
        """
        Test GET with with user, but only projects with data imports.

        It should render the page with all projects, where user is an
        administrator. Those projects must also have data imports
        """
        projects = [self.project_2]

        self.request.user = self.user
        self.request.GET['filter'] = 'with-data-imports-only'
        response = self.view(self.request).render()

        rendered = render_to_string(
            'di_index.html',
            {
                'PLATFORM_NAME': get_current_site(self.request).name,
                'GEOKEY_VERSION': version.get_version(),
                'user': self.request.user,
                'messages': get_messages(self.request),
                'filters': self.filters,
                'projects': projects,
                'request': {
                    'GET': {
                        'filter': self.request.GET.get('filter')
                    }
                }
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )


class AllDataImportsPageTest(TestCase):
    """Test all data imports page."""

    def setUp(self):
        """Set up test."""
        self.request = HttpRequest()
        self.request.method = 'GET'
        self.view = AllDataImportsPage.as_view()

        self.user = UserFactory.create()
        self.contributor = UserFactory.create()
        self.admin = UserFactory.create()

        self.project = ProjectFactory.create(
            add_admins=[self.admin],
            add_contributors=[self.contributor]
        )

        setattr(self.request, 'session', 'session')
        messages = FallbackStorage(self.request)
        setattr(self.request, '_messages', messages)

    def test_get_with_anonymous(self):
        """
        Test GET with with anonymous.

        It should redirect to login page.
        """
        self.request.user = AnonymousUser()
        response = self.view(self.request, project_id=self.project.id)

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

    def test_get_with_user(self):
        """
        Test GET with with user.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.user
        response = self.view(self.request, project_id=self.project.id).render()

        rendered = render_to_string(
            'di_all_dataimports.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Project')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_contributor(self):
        """
        Test GET with with contributor.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.contributor
        response = self.view(self.request, project_id=self.project.id).render()

        rendered = render_to_string(
            'di_all_dataimports.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Permission denied.',
                'error_description': no_rights_to_access_msg
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_admin(self):
        """
        Test GET with with admin.

        It should render the page with a project.
        """
        self.request.user = self.admin
        response = self.view(self.request, project_id=self.project.id).render()

        rendered = render_to_string(
            'di_all_dataimports.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'project': self.project
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_when_no_project(self):
        """
        Test GET with with admin, when project does not exist.

        It should inform user that project does not exist.
        """
        self.request.user = self.admin
        response = self.view(
            self.request,
            project_id=self.project.id + 123
        ).render()

        rendered = render_to_string(
            'di_all_dataimports.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Project')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )


class AddDataImportPageTest(TestCase):
    """Test add data import page."""

    def setUp(self):
        """Set up test."""
        self.factory = RequestFactory()
        self.request = HttpRequest()
        self.view = AddDataImportPage.as_view()

        self.user = UserFactory.create()
        self.contributor = UserFactory.create()
        self.admin = UserFactory.create()

        self.project = ProjectFactory.create(
            add_admins=[self.admin],
            add_contributors=[self.contributor]
        )
        self.category = CategoryFactory.create(
            project=self.project
        )

        self.data = {
            'name': 'Test Import',
            'description': '',
            'file': File(open(file_helpers.get_csv_file().name)),
            'category_create': 'true'
        }
        self.url = reverse('geokey_dataimports:dataimport_add', kwargs={
            'project_id': self.project.id
        })

        setattr(self.request, 'session', 'session')
        messages = FallbackStorage(self.request)
        setattr(self.request, '_messages', messages)

    def tearDown(self):
        """Tear down test."""
        for dataimport in DataImport.objects.all():
            if dataimport.file:
                dataimport.file.delete()

    def test_get_with_anonymous(self):
        """
        Test GET with with anonymous.

        It should redirect to login page.
        """
        self.request.user = AnonymousUser()
        self.request.method = 'GET'
        response = self.view(self.request, project_id=self.project.id)

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

    def test_get_with_user(self):
        """
        Test GET with with user.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.user
        self.request.method = 'GET'
        response = self.view(self.request, project_id=self.project.id).render()

        form = DataImportForm()
        rendered = render_to_string(
            'di_add_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Project')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_contributor(self):
        """
        Test GET with with contributor.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.contributor
        self.request.method = 'GET'
        response = self.view(self.request, project_id=self.project.id).render()

        form = DataImportForm()
        rendered = render_to_string(
            'di_add_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'error': 'Permission denied.',
                'error_description': no_rights_to_access_msg
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_admin(self):
        """
        Test GET with with admin.

        It should render the page with a project.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(self.request, project_id=self.project.id).render()

        form = DataImportForm()
        rendered = render_to_string(
            'di_add_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'project': self.project
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_when_no_project(self):
        """
        Test GET with with admin, when project does not exist.

        It should inform user that project does not exist.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id + 123
        ).render()

        form = DataImportForm()
        rendered = render_to_string(
            'di_add_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Project'),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_post_with_anonymous(self):
        """
        Test POST with with anonymous.

        It should redirect to login page.
        """
        request = self.factory.post(self.url, self.data)
        request.user = AnonymousUser()

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(request, project_id=self.project.id)

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

    def test_post_with_user(self):
        """
        Test POST with with user.

        It should not allow to add new data imports, when user is not an
        administrator.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.user

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(request, project_id=self.project.id).render()

        form = DataImportForm(data=self.data)
        rendered = render_to_string(
            'di_add_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Project')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataImport.objects.count(), 0)
        self.assertEqual(DataField.objects.count(), 0)
        self.assertEqual(DataFeature.objects.count(), 0)

    def test_post_with_contributor(self):
        """
        Test POST with with contributor.

        It should not allow to add new data imports, when user is not an
        administrator.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.contributor

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(request, project_id=self.project.id).render()

        form = DataImportForm(data=self.data)
        rendered = render_to_string(
            'di_add_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'error': 'Permission denied.',
                'error_description': no_rights_to_access_msg
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataImport.objects.count(), 0)
        self.assertEqual(DataField.objects.count(), 0)
        self.assertEqual(DataFeature.objects.count(), 0)

    def test_post_with_admin_when_creating_new_category(self):
        """
        Test POST with with admin, when creating a new category.

        It should add new data import, when user is an administrator. Also, it
        should redirect to a page to add a new category.
        """
        self.data['category_create'] = 'true'
        self.data['category'] = None
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(request, project_id=self.project.id)

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse(
                'geokey_dataimports:dataimport_create_category',
                kwargs={
                    'project_id': self.project.id,
                    'dataimport_id': DataImport.objects.first().id
                }
            ),
            response['location']
        )
        self.assertEqual(DataImport.objects.count(), 1)
        self.assertEqual(DataField.objects.count(), 3)
        self.assertEqual(DataFeature.objects.count(), 3)

    def test_post_with_admin_when_attaching_existing_category(self):
        """
        Test POST with with admin, when selecting category.

        It should add new data import, when user is an administrator. Also, it
        should redirect to a page to assing fields.
        """
        self.data['category_create'] = 'false'
        self.data['category'] = self.category.id
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(request, project_id=self.project.id)

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse(
                'geokey_dataimports:dataimport_assign_fields',
                kwargs={
                    'project_id': self.project.id,
                    'dataimport_id': DataImport.objects.first().id
                }
            ),
            response['location']
        )
        self.assertEqual(DataImport.objects.count(), 1)
        self.assertEqual(DataField.objects.count(), 3)
        self.assertEqual(DataFeature.objects.count(), 3)

    def test_post_when_wrong_data(self):
        """
        Test POST with with admin, when data is wrong.

        It should inform user that data is wrong.
        """
        self.data['name'] = ''
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(request, project_id=self.project.id).render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DataImport.objects.count(), 0)
        self.assertEqual(DataField.objects.count(), 0)
        self.assertEqual(DataFeature.objects.count(), 0)

    def test_post_when_no_project(self):
        """
        Test POST with with admin, when project does not exist.

        It should inform user that project does not exist.
        """
        self.data['category_create'] = 'true'
        self.data['category'] = None
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id + 123
        ).render()

        form = DataImportForm(data=self.data)
        rendered = render_to_string(
            'di_add_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Project')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataImport.objects.count(), 0)
        self.assertEqual(DataField.objects.count(), 0)
        self.assertEqual(DataFeature.objects.count(), 0)

    def test_post_when_no_category(self):
        """
        Test POST with with admin, when category does not exist.

        It should add new data import, when user is an administrator. Also, it
        should redirect to a page to create a new category and inform user that
        category was not found.
        """
        self.data['category_create'] = 'false'
        self.data['category'] = self.category.id + 123
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(request, project_id=self.project.id)

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse(
                'geokey_dataimports:dataimport_create_category',
                kwargs={
                    'project_id': self.project.id,
                    'dataimport_id': DataImport.objects.first().id
                }
            ),
            response['location']
        )
        self.assertEqual(DataImport.objects.count(), 1)
        self.assertEqual(DataField.objects.count(), 3)
        self.assertEqual(DataFeature.objects.count(), 3)

    def test_post_when_project_is_locked(self):
        """
        Test POST with with admin, when project is locked.

        It should not add new data import, when project is locked.
        """
        self.project.islocked = True
        self.project.save()

        self.data['category_create'] = 'true'
        self.data['category'] = None
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(request, project_id=self.project.id).render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(DataImport.objects.count(), 0)
        self.assertEqual(DataField.objects.count(), 0)
        self.assertEqual(DataFeature.objects.count(), 0)


class SingleDataImportPageTest(TestCase):
    """Test single data import page."""

    def setUp(self):
        """Set up test."""
        self.factory = RequestFactory()
        self.request = HttpRequest()
        self.view = SingleDataImportPage.as_view()

        self.user = UserFactory.create()
        self.contributor = UserFactory.create()
        self.admin = UserFactory.create()

        self.project = ProjectFactory.create(
            add_admins=[self.admin],
            add_contributors=[self.contributor]
        )
        self.category = CategoryFactory.create(
            project=self.project
        )
        self.dataimport = DataImportFactory.create(
            project=self.project,
            category=None
        )

        self.data = {
            'name': 'Test Import',
            'description': '',
            'category': self.category.id
        }
        self.url = reverse('geokey_dataimports:single_dataimport', kwargs={
            'project_id': self.project.id,
            'dataimport_id': self.dataimport.id
        })

        setattr(self.request, 'session', 'session')
        messages = FallbackStorage(self.request)
        setattr(self.request, '_messages', messages)

    def tearDown(self):
        """Tear down test."""
        for dataimport in DataImport.objects.all():
            if dataimport.file:
                dataimport.file.delete()

    def test_get_with_anonymous(self):
        """
        Test GET with with anonymous.

        It should redirect to login page.
        """
        self.request.user = AnonymousUser()
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

    def test_get_with_user(self):
        """
        Test GET with with user.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.user
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = DataImportForm()
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_contributor(self):
        """
        Test GET with with contributor.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.contributor
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = DataImportForm()
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_admin(self):
        """
        Test GET with with admin.

        It should render the page with a project and data import.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = DataImportForm()
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'project': self.project,
                'dataimport': self.dataimport
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_when_no_project(self):
        """
        Test GET with with admin, when project does not exist.

        It should inform user that data import does not exist.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id + 123,
            dataimport_id=self.dataimport.id
        ).render()

        form = DataImportForm()
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import'),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_when_no_dataimport(self):
        """
        Test GET with with admin, when data import does not exist.

        It should inform user that data import does not exist.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id + 123
        ).render()

        form = DataImportForm()
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import'),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_post_with_anonymous(self):
        """
        Test POST with with anonymous.

        It should redirect to login page.
        """
        request = self.factory.post(self.url, self.data)
        request.user = AnonymousUser()

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertEqual(reference.name, self.dataimport.name)
        self.assertEqual(reference.description, self.dataimport.description)

    def test_post_with_user(self):
        """
        Test POST with with user.

        It should not allow to edit a data import, when user is not an
        administrator.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.user

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = DataImportForm(data=self.data)
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertEqual(reference.name, self.dataimport.name)
        self.assertEqual(reference.description, self.dataimport.description)

    def test_post_with_contributor(self):
        """
        Test POST with with contributor.

        It should not allow to edit a data import, when user is not an
        administrator.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.contributor

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = DataImportForm(data=self.data)
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertEqual(reference.name, self.dataimport.name)
        self.assertEqual(reference.description, self.dataimport.description)

    def test_post_with_admin(self):
        """
        Test POST with with admin.

        It should edit a data import, when user is an administrator.
        """
        self.dataimport.category = self.category
        self.dataimport.save()

        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = DataImportForm(data=self.data)
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'project': self.project,
                'dataimport': self.dataimport
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertEqual(reference.name, self.data.get('name'))
        self.assertEqual(reference.description, self.data.get('description'))

    def test_post_with_admin_when_selecting_category(self):
        """
        Test POST with with admin, when selecting category.

        It should edit a data import and select a category, when user is an
        administrator. Also, it should redirect to a page to assign fields.
        """
        self.data['category'] = self.category.id
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse(
                'geokey_dataimports:dataimport_assign_fields',
                kwargs={
                    'project_id': self.project.id,
                    'dataimport_id': self.dataimport.id
                }
            ),
            response['location']
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertEqual(reference.name, self.data.get('name'))
        self.assertEqual(reference.description, self.data.get('description'))

    def test_post_when_wrong_data(self):
        """
        Test POST with with admin, when data is wrong.

        It should inform user that data is wrong.
        """
        self.data['name'] = ''
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = DataImportForm(data=self.data)
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'project': self.project,
                'dataimport': self.dataimport
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertEqual(reference.name, self.dataimport.name)
        self.assertEqual(reference.description, self.dataimport.description)

    def test_post_when_no_project(self):
        """
        Test POST with with admin, when project does not exist.

        It should inform user that data import does not exist.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id + 123,
            dataimport_id=self.dataimport.id
        ).render()

        form = DataImportForm(data=self.data)
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertEqual(reference.name, self.dataimport.name)
        self.assertEqual(reference.description, self.dataimport.description)

    def test_post_when_no_dataimport(self):
        """
        Test POST with with admin, when data import does not exist.

        It should inform user that data import does not exist.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id + 123
        ).render()

        form = DataImportForm(data=self.data)
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertEqual(reference.name, self.dataimport.name)
        self.assertEqual(reference.description, self.dataimport.description)

    def test_post_when_no_category(self):
        """
        Test POST with with admin, when category does not exist.

        It should inform user that category does not exist. Also, it should
        redirect to a page to create a new category.
        """
        self.data['category'] = self.category.id + 123
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse(
                'geokey_dataimports:dataimport_create_category',
                kwargs={
                    'project_id': self.project.id,
                    'dataimport_id': self.dataimport.id
                }
            ),
            response['location']
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertEqual(reference.name, self.data.get('name'))
        self.assertEqual(reference.description, self.data.get('description'))

    def test_post_when_project_is_locked(self):
        """
        Test POST with with admin, when project is locked.

        It should not edit a data import, when project is locked.
        """
        self.project.islocked = True
        self.project.save()

        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = DataImportForm(data=self.data)
        rendered = render_to_string(
            'di_single_dataimport.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'project': self.project,
                'dataimport': self.dataimport
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertEqual(reference.name, self.dataimport.name)
        self.assertEqual(reference.description, self.dataimport.description)


class DataImportCreateCategoryPageTest(TestCase):
    """Test data import create category page."""

    def setUp(self):
        """Set up test."""
        self.factory = RequestFactory()
        self.request = HttpRequest()
        self.view = DataImportCreateCategoryPage.as_view()

        self.user = UserFactory.create()
        self.contributor = UserFactory.create()
        self.admin = UserFactory.create()

        self.project = ProjectFactory.create(
            add_admins=[self.admin],
            add_contributors=[self.contributor]
        )
        self.category = CategoryFactory.create(
            project=self.project
        )
        self.dataimport = DataImportFactory.create(
            project=self.project,
            category=None
        )

        self.data = {}
        self.url = reverse(
            'geokey_dataimports:dataimport_create_category',
            kwargs={
                'project_id': self.project.id,
                'dataimport_id': self.dataimport.id
            }
        )

        setattr(self.request, 'session', 'session')
        messages = FallbackStorage(self.request)
        setattr(self.request, '_messages', messages)

    def tearDown(self):
        """Tear down test."""
        for dataimport in DataImport.objects.all():
            if dataimport.file:
                dataimport.file.delete()

    def test_get_with_anonymous(self):
        """
        Test GET with with anonymous.

        It should redirect to login page.
        """
        self.request.user = AnonymousUser()
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

    def test_get_with_user(self):
        """
        Test GET with with user.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.user
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = CategoryForm()
        rendered = render_to_string(
            'di_create_category.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_contributor(self):
        """
        Test GET with with contributor.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.contributor
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = CategoryForm()
        rendered = render_to_string(
            'di_create_category.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_admin(self):
        """
        Test GET with with admin.

        It should render the page with a project and data import.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = CategoryForm()
        rendered = render_to_string(
            'di_create_category.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'project': self.project,
                'dataimport': self.dataimport
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_when_no_project(self):
        """
        Test GET with with admin, when project does not exist.

        It should inform user that data import does not exist.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id + 123,
            dataimport_id=self.dataimport.id
        ).render()

        form = CategoryForm()
        rendered = render_to_string(
            'di_create_category.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import'),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_when_no_dataimport(self):
        """
        Test GET with with admin, when data import does not exist.

        It should inform user that data import does not exist.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id + 123
        ).render()

        form = CategoryForm()
        rendered = render_to_string(
            'di_create_category.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import'),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_post_with_anonymous(self):
        """
        Test POST with with anonymous.

        It should redirect to login page.
        """
        request = self.factory.post(self.url, self.data)
        request.user = AnonymousUser()

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.category)
        self.assertIsNone(reference.keys)

    def test_post_with_user(self):
        """
        Test POST with with user.

        It should not allow to create category, when user is not an
        administrator.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.user

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = CategoryForm(data=self.data)
        rendered = render_to_string(
            'di_create_category.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.category)
        self.assertIsNone(reference.keys)

    def test_post_with_contributor(self):
        """
        Test POST with with contributor.

        It should not allow to create category, when user is not an
        administrator.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.contributor

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = CategoryForm(data=self.data)
        rendered = render_to_string(
            'di_create_category.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.category)
        self.assertIsNone(reference.keys)

    def test_post_when_no_project(self):
        """
        Test POST with with admin, when project does not exist.

        It should inform user that data import does not exist.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id + 123,
            dataimport_id=self.dataimport.id
        ).render()

        form = CategoryForm(data=self.data)
        rendered = render_to_string(
            'di_create_category.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.category)
        self.assertIsNone(reference.keys)

    def test_post_when_no_dataimport(self):
        """
        Test POST with with admin, when data import does not exist.

        It should inform user that data import does not exist.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id + 123
        ).render()

        form = CategoryForm(data=self.data)
        rendered = render_to_string(
            'di_create_category.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.category)
        self.assertIsNone(reference.keys)

    def test_post_when_project_is_locked(self):
        """
        Test POST with with admin, when project is locked.

        It should not create category, when project is locked.
        """
        self.project.islocked = True
        self.project.save()

        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        form = CategoryForm(data=self.data)
        rendered = render_to_string(
            'di_create_category.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': request.user,
                'messages': get_messages(request),
                'form': form,
                'project': self.project,
                'dataimport': self.dataimport
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.category)
        self.assertIsNone(reference.keys)


class DataImportAssignFieldsPageTest(TestCase):
    """Test data import assign fields page."""

    def setUp(self):
        """Set up test."""
        self.factory = RequestFactory()
        self.request = HttpRequest()
        self.view = DataImportAssignFieldsPage.as_view()

        self.user = UserFactory.create()
        self.contributor = UserFactory.create()
        self.admin = UserFactory.create()

        self.project = ProjectFactory.create(
            add_admins=[self.admin],
            add_contributors=[self.contributor]
        )
        self.category = CategoryFactory.create(
            project=self.project
        )
        self.dataimport = DataImportFactory.create(
            project=self.project
        )

        self.data = {}
        self.url = reverse(
            'geokey_dataimports:dataimport_assign_fields',
            kwargs={
                'project_id': self.project.id,
                'dataimport_id': self.dataimport.id
            }
        )

        setattr(self.request, 'session', 'session')
        messages = FallbackStorage(self.request)
        setattr(self.request, '_messages', messages)

    def tearDown(self):
        """Tear down test."""
        for dataimport in DataImport.objects.all():
            if dataimport.file:
                dataimport.file.delete()

    def test_get_with_anonymous(self):
        """
        Test GET with with anonymous.

        It should redirect to login page.
        """
        self.request.user = AnonymousUser()
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

    def test_get_with_user(self):
        """
        Test GET with with user.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.user
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_assign_fields.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_contributor(self):
        """
        Test GET with with contributor.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.contributor
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_assign_fields.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_admin(self):
        """
        Test GET with with admin.

        It should render the page with a project and data import.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_assign_fields.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'project': self.project,
                'dataimport': self.dataimport
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_when_no_project(self):
        """
        Test GET with with admin, when project does not exist.

        It should inform user that data import does not exist.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id + 123,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_assign_fields.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import'),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_when_no_dataimport(self):
        """
        Test GET with with admin, when data import does not exist.

        It should inform user that data import does not exist.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id + 123
        ).render()

        rendered = render_to_string(
            'di_assign_fields.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import'),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_post_with_anonymous(self):
        """
        Test POST with with anonymous.

        It should redirect to login page.
        """
        request = self.factory.post(self.url, self.data)
        request.user = AnonymousUser()

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.keys)

    def test_post_with_user(self):
        """
        Test POST with with user.

        It should not allow to assign fields, when user is not an
        administrator.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.user

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_assign_fields.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.keys)

    def test_post_with_contributor(self):
        """
        Test POST with with contributor.

        It should not allow to assign fields, when user is not an
        administrator.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.contributor

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_assign_fields.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.keys)

    def test_post_when_no_project(self):
        """
        Test POST with with admin, when project does not exist.

        It should inform user that data import does not exist.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id + 123,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_assign_fields.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.keys)

    def test_post_when_no_dataimport(self):
        """
        Test POST with with admin, when data import does not exist.

        It should inform user that data import does not exist.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id + 123
        ).render()

        rendered = render_to_string(
            'di_assign_fields.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.keys)

    def test_post_when_no_category(self):
        """
        Test POST with with admin, when category is not associated.

        It should not assign fields, when category is not associated.
        """
        self.dataimport.category = None
        self.dataimport.save()

        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_assign_fields.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': request.user,
                'messages': get_messages(request),
                'project': self.project,
                'dataimport': self.dataimport
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.keys)

    def test_post_when_project_is_locked(self):
        """
        Test POST with with admin, when project is locked.

        It should not assign fields, when project is locked.
        """
        self.project.islocked = True
        self.project.save()

        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_assign_fields.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': request.user,
                'messages': get_messages(request),
                'project': self.project,
                'dataimport': self.dataimport
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

        reference = DataImport.objects.get(pk=self.dataimport.id)
        self.assertIsNone(reference.keys)


class DataImportAllDataFeaturesPageTest(TestCase):
    """Test data import all data features page."""

    def setUp(self):
        """Set up test."""
        self.factory = RequestFactory()
        self.request = HttpRequest()
        self.view = DataImportAllDataFeaturesPage.as_view()

        self.user = UserFactory.create()
        self.contributor = UserFactory.create()
        self.admin = UserFactory.create()

        self.project = ProjectFactory.create(
            add_admins=[self.admin],
            add_contributors=[self.contributor]
        )
        self.category = CategoryFactory.create(project=self.project)
        self.dataimport = DataImportFactory.create(
            keys=['Name'],
            project=self.project,
            category=self.category
        )
        TextFieldFactory.create(
            key='Name',
            category=self.category
        )

        ids = []
        self.datafeatures = {
            'type': 'FeatureCollection',
            'features': []
        }
        for datafeature in self.dataimport.datafeatures.all():
            self.datafeatures['features'].append({
                'type': 'Feature',
                'id': datafeature.id,
                'geometry': json.loads(datafeature.geometry.json)
            })
            ids.append(datafeature.id)

        self.data = {
            'ids': json.dumps(ids)
        }
        self.url = reverse(
            'geokey_dataimports:dataimport_all_datafeatures',
            kwargs={
                'project_id': self.project.id,
                'dataimport_id': self.dataimport.id
            }
        )

        setattr(self.request, 'session', 'session')
        messages = FallbackStorage(self.request)
        setattr(self.request, '_messages', messages)

    def tearDown(self):
        """Tear down test."""
        for dataimport in DataImport.objects.all():
            if dataimport.file:
                dataimport.file.delete()

    def test_get_with_anonymous(self):
        """
        Test GET with with anonymous.

        It should redirect to login page.
        """
        self.request.user = AnonymousUser()
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

    def test_get_with_user(self):
        """
        Test GET with with user.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.user
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_contributor(self):
        """
        Test GET with with contributor.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.contributor
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_with_admin(self):
        """
        Test GET with with admin.

        It should render the page with a project, data import and all data
        features.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'project': self.project,
                'dataimport': self.dataimport,
                'datafeatures': self.datafeatures
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_when_no_project(self):
        """
        Test GET with with admin, when project does not exist.

        It should inform user that data import does not exist.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id + 123,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import'),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_get_when_no_dataimport(self):
        """
        Test GET with with admin, when data import does not exist.

        It should inform user that data import does not exist.
        """
        self.request.user = self.admin
        self.request.method = 'GET'
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id + 123
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import'),
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )

    def test_post_with_anonymous(self):
        """
        Test POST with with anonymous.

        It should redirect to login page.
        """
        request = self.factory.post(self.url, self.data)
        request.user = AnonymousUser()

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])
        self.assertEqual(DataFeature.objects.filter(imported=True).count(), 0)
        self.assertEqual(Observation.objects.count(), 0)

    def test_post_with_user(self):
        """
        Test POST with with user.

        It should not allow to convert data features to contributions, when
        user is not an administrator.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.user

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataFeature.objects.filter(imported=True).count(), 0)
        self.assertEqual(Observation.objects.count(), 0)

    def test_post_with_contributor(self):
        """
        Test POST with with contributor.

        It should not allow to convert data features to contributions, when
        user is not an administrator.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.contributor

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataFeature.objects.filter(imported=True).count(), 0)
        self.assertEqual(Observation.objects.count(), 0)

    def test_post_with_admin(self):
        """
        Test POST with with admin.

        It should convert data features to contributions, when user is an
        administrator.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse(
                'geokey_dataimports:single_dataimport',
                kwargs={
                    'project_id': self.project.id,
                    'dataimport_id': self.dataimport.id
                }
            ),
            response['location']
        )
        self.assertEqual(DataFeature.objects.filter(imported=True).count(), 3)
        self.assertEqual(Observation.objects.count(), 3)

    def test_post_when_no_ids(self):
        """
        Test POST with with admin, when no IDs are provided.

        It should not allow to convert data features to contributions, when
        no IDs are provided in the request.
        """
        self.data = {}
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse(
                'geokey_dataimports:single_dataimport',
                kwargs={
                    'project_id': self.project.id,
                    'dataimport_id': self.dataimport.id
                }
            ),
            response['location']
        )
        self.assertEqual(DataFeature.objects.filter(imported=True).count(), 0)
        self.assertEqual(Observation.objects.count(), 0)

    def test_post_when_no_project(self):
        """
        Test POST with with admin, when project does not exist.

        It should inform user that data import does not exist.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id + 123,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataFeature.objects.filter(imported=True).count(), 0)
        self.assertEqual(Observation.objects.count(), 0)

    def test_post_when_no_dataimport(self):
        """
        Test POST with with admin, when data import does not exist.

        It should inform user that data import does not exist.
        """
        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id + 123
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(request).name,
                'user': request.user,
                'messages': get_messages(request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataFeature.objects.filter(imported=True).count(), 0)
        self.assertEqual(Observation.objects.count(), 0)

    def test_post_when_no_category(self):
        """
        Test POST with with admin, when category is not associated.

        It should not allow to convert data features to contributions, when
        category is not associated.
        """
        self.dataimport.category = None
        self.dataimport.save()

        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': request.user,
                'messages': get_messages(request),
                'project': self.project,
                'dataimport': self.dataimport,
                'datafeatures': self.datafeatures
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataFeature.objects.filter(imported=True).count(), 0)
        self.assertEqual(Observation.objects.count(), 0)

    def test_post_when_no_fields(self):
        """
        Test POST with with admin, when fields are not assigned.

        It should not allow to convert data features to contributions, when
        fields are not assigned.
        """
        self.dataimport.keys = None
        self.dataimport.save()

        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': request.user,
                'messages': get_messages(request),
                'project': self.project,
                'dataimport': self.dataimport,
                'datafeatures': self.datafeatures
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataFeature.objects.filter(imported=True).count(), 0)
        self.assertEqual(Observation.objects.count(), 0)

    def test_post_when_project_is_locked(self):
        """
        Test POST with with admin, when project is locked.

        It should not assign fields, when project is locked.
        """
        self.project.islocked = True
        self.project.save()

        request = self.factory.post(self.url, self.data)
        request.user = self.admin

        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)

        response = self.view(
            request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'di_all_datafeatures.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': request.user,
                'messages': get_messages(request),
                'project': self.project,
                'dataimport': self.dataimport,
                'datafeatures': self.datafeatures
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataFeature.objects.filter(imported=True).count(), 0)
        self.assertEqual(Observation.objects.count(), 0)


class RemoveDataImportPageTest(TestCase):
    """Test remove data import page."""

    def setUp(self):
        """Set up test."""
        self.request = HttpRequest()
        self.request.method = 'GET'
        self.view = RemoveDataImportPage.as_view()

        self.user = UserFactory.create()
        self.contributor = UserFactory.create()
        self.admin = UserFactory.create()

        self.project = ProjectFactory.create(
            add_admins=[self.admin],
            add_contributors=[self.contributor]
        )
        self.dataimport = DataImportFactory.create(project=self.project)
        self.file = self.dataimport.file.path

        setattr(self.request, 'session', 'session')
        messages = FallbackStorage(self.request)
        setattr(self.request, '_messages', messages)

    def tearDown(self):
        """Tear down test."""
        for dataimport in DataImport.objects.all():
            if dataimport.file:
                dataimport.file.delete()

        if os.path.isfile(self.file):
            os.remove(self.file)

    def test_get_with_anonymous(self):
        """
        Test GET with with anonymous.

        It should redirect to login page.
        """
        self.request.user = AnonymousUser()
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/account/login/', response['location'])

    def test_get_with_user(self):
        """
        Test GET with with user.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.user
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'base.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataImport.objects.count(), 1)

    def test_get_with_contributor(self):
        """
        Test GET with with contributor.

        It should not allow to access the page, when user is not an
        administrator.
        """
        self.request.user = self.contributor
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'base.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataImport.objects.count(), 1)

    def test_get_with_admin(self):
        """
        Test GET with with admin.

        It should remove import and redirect to all imports of a project.
        """
        self.request.user = self.admin
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse(
                'geokey_dataimports:all_dataimports',
                kwargs={'project_id': self.project.id}
            ),
            response['location']
        )
        self.assertEqual(DataImport.objects.count(), 0)

    def test_get_when_no_project(self):
        """
        Test GET with with admin, when project does not exist.

        It should inform user that data import does not exist.
        """
        self.request.user = self.admin
        response = self.view(
            self.request,
            project_id=self.project.id + 123,
            dataimport_id=self.dataimport.id
        ).render()

        rendered = render_to_string(
            'base.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataImport.objects.count(), 1)

    def test_get_when_no_import(self):
        """
        Test GET with with admin, when import does not exist.

        It should inform user that data import does not exist.
        """
        self.request.user = self.admin
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id + 123
        ).render()

        rendered = render_to_string(
            'base.html',
            {
                'GEOKEY_VERSION': version.get_version(),
                'PLATFORM_NAME': get_current_site(self.request).name,
                'user': self.request.user,
                'messages': get_messages(self.request),
                'error': 'Not found.',
                'error_description': does_not_exist_msg('Data import')
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            render_helpers.remove_csrf(response.content.decode('utf-8')),
            rendered
        )
        self.assertEqual(DataImport.objects.count(), 1)

    def test_get_when_project_is_locked(self):
        """
        Test GET with with admin, when project is locked.

        It should inform user that the project is locked and redirect to the
        same data import.
        """
        self.project.islocked = True
        self.project.save()

        self.request.user = self.admin
        response = self.view(
            self.request,
            project_id=self.project.id,
            dataimport_id=self.dataimport.id
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse(
                'geokey_dataimports:single_dataimport',
                kwargs={
                    'project_id': self.project.id,
                    'dataimport_id': self.dataimport.id
                }
            ),
            response['location']
        )
        self.assertEqual(DataImport.objects.count(), 1)
