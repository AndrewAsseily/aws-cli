# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Multi-role login against the Sign-In stub APIs.

Signs in through the browser, lists the roles the identity can assume, lets the
user pick some, and writes an ordinary CLI profile plus a credential cache
record for each one. Not for merge.
"""

import base64
import datetime
import hashlib
import json
import os
import secrets
import string
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import uuid

from awscrt.crypto import EC, ECExportFormat, ECType
from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding.key_bindings import KeyBindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl

from awscli.customizations.commands import BasicCommand
from awscli.customizations.configure.writer import ConfigFileWriter
from awscli.customizations.sso.utils import (
    AuthCodeFetcher,
    open_browser_with_original_ld_path,
)
from awscli.customizations.utils import uni_print

CLIENT_ID = 'arn:aws:signin:::devtools/same-device'
TOKEN_EXCHANGE = 'urn:ietf:params:oauth:grant-type:token-exchange'
VISIBLE_ROWS = 12


class StubError(Exception):
    pass


class StubClient:
    def __init__(self, base_url):
        self._base = base_url.rstrip('/')

    def _send(self, request):
        try:
            with urllib.request.urlopen(request) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as error:
            body = error.read().decode('utf-8', 'replace')
            try:
                detail = json.loads(body)
                message = detail.get('error_description') or detail.get(
                    'message', body
                )
            except ValueError:
                message = body
            raise StubError(f'{error.code} {message}') from None
        except urllib.error.URLError as error:
            raise StubError(str(error.reason)) from None

    def post(self, path, body, token=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        return self._send(
            urllib.request.Request(
                f'{self._base}{path}',
                data=json.dumps(body).encode('utf-8'),
                headers=headers,
                method='POST',
            )
        )

    def get(self, path, token):
        return self._send(
            urllib.request.Request(
                f'{self._base}{path}',
                headers={'Authorization': f'Bearer {token}'},
                method='GET',
            )
        )

    def authorize_url(self, redirect_uri, state, challenge):
        query = urllib.parse.urlencode(
            {
                'response_type': 'code',
                'client_id': CLIENT_ID,
                'redirect_uri': redirect_uri,
                'state': state,
                'code_challenge_method': 'SHA-256',
                'scope': 'openid',
            }
        )
        return f'{self._base}/v1/authorize?{query}&code_challenge={challenge}'

    def redeem_code(self, code, verifier, redirect_uri):
        return self.post(
            '/v1/token',
            {
                'grantType': 'authorization_code',
                'clientId': CLIENT_ID,
                'code': code,
                'codeVerifier': verifier,
                'redirectUri': redirect_uri,
            },
        )

    def list_roles(self, token, keyword=None):
        roles = []
        next_token = None
        while True:
            params = {}
            if keyword:
                params['keyword'] = keyword
            if next_token:
                params['nextToken'] = next_token
            path = '/v1/listRoles'
            if params:
                path += '?' + urllib.parse.urlencode(params)
            page = self.get(path, token)
            roles.extend(page.get('roles', []))
            next_token = page.get('nextToken')
            if not next_token:
                return roles

    def exchange_role(self, token, role_arn):
        return self.post(
            '/v1/token',
            {'grantType': TOKEN_EXCHANGE, 'roleArn': role_arn},
            token=token,
        )


def sign_in(client):
    """Runs the browser flow and returns the identity access token."""
    fetcher = AuthCodeFetcher()
    redirect_uri = fetcher.redirect_uri_with_port()
    state = str(uuid.uuid4())
    verifier = ''.join(
        secrets.choice(string.ascii_letters + string.digits + '-._~')
        for _ in range(64)
    )
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip('=')
    )

    url = client.authorize_url(redirect_uri, state, challenge)
    uni_print(
        f'\nOpening your browser to sign in.\nIf it does not open:\n\n  {url}\n\n'
    )
    try:
        open_browser_with_original_ld_path(url)
    except Exception:
        pass

    code, returned_state = fetcher.get_auth_code_and_state()
    if returned_state != state:
        raise StubError('state parameter did not match')
    if not code:
        raise StubError('no authorization code returned')

    result = client.redeem_code(code, verifier, redirect_uri)
    return result['accessToken']


def pick_roles(roles, initial_filter=''):
    """Filterable checklist. Returns the selected roles, or [] if cancelled."""
    if not sys.stdout.isatty():
        raise StubError('selecting roles needs an interactive terminal')

    widths = (
        max(len(r['account_name']) for r in roles),
        max(len(r['role_name']) for r in roles),
    )
    state = {'cursor': 0, 'top': 0, 'shown': list(roles), 'cancelled': False}
    checked = {}

    def key_of(role):
        return (role['account_id'], role['role_name'])

    def refilter(text):
        needle = text.strip().lower()
        state['shown'] = [
            r
            for r in roles
            if not needle
            or needle in r['account_name'].lower()
            or needle in r['role_name'].lower()
            or needle in r['account_id']
        ]
        state['cursor'] = 0
        state['top'] = 0

    filter_buffer = Buffer(multiline=False)
    filter_buffer.on_text_changed += lambda _: refilter(filter_buffer.text)
    if initial_filter:
        filter_buffer.text = initial_filter

    def status():
        return [
            (
                '',
                '  {} of {} shown, {} selected'.format(
                    len(state['shown']), len(roles), len(checked)
                ),
            )
        ]

    def rows():
        shown = state['shown']
        if not shown:
            return [('', '  no roles match')]
        top = state['top']
        out = []
        for index in range(top, min(top + VISIBLE_ROWS, len(shown))):
            role = shown[index]
            box = '[x]' if key_of(role) in checked else '[ ]'
            cursor = '>' if index == state['cursor'] else ' '
            text = '{} {} {:<{}}  {:<12}  {:<{}}'.format(
                cursor,
                box,
                role['account_name'],
                widths[0],
                role['account_id'],
                role['role_name'],
                widths[1],
            )
            style = 'reverse' if index == state['cursor'] else ''
            out.append((style, text + '\n'))
        return out

    def move(delta):
        shown = state['shown']
        if not shown:
            return
        state['cursor'] = max(0, min(len(shown) - 1, state['cursor'] + delta))
        if state['cursor'] < state['top']:
            state['top'] = state['cursor']
        elif state['cursor'] >= state['top'] + VISIBLE_ROWS:
            state['top'] = state['cursor'] - VISIBLE_ROWS + 1

    keys = KeyBindings()

    @keys.add('up')
    def _(event):
        move(-1)

    @keys.add('down')
    def _(event):
        move(1)

    @keys.add(' ')
    def _(event):
        shown = state['shown']
        if not shown:
            return
        role = shown[state['cursor']]
        key = key_of(role)
        if key in checked:
            del checked[key]
        else:
            checked[key] = role

    @keys.add('enter')
    def _(event):
        event.app.exit()

    @keys.add('c-c')
    def _(event):
        state['cancelled'] = True
        event.app.exit()

    header = '      {:<{}}  {:<12}  {}'.format(
        'ACCOUNT', widths[0], 'ID', 'ROLE'
    )
    layout = Layout(
        HSplit(
            [
                Window(
                    FormattedTextControl(
                        lambda: [
                            (
                                '',
                                'Select roles.  SPACE toggle   ENTER confirm   '
                                'CTRL-C cancel',
                            )
                        ]
                    ),
                    height=1,
                ),
                Window(
                    BufferControl(buffer=filter_buffer),
                    height=1,
                    get_line_prefix=lambda *_: 'Filter: ',
                ),
                Window(FormattedTextControl(status), height=1),
                Window(FormattedTextControl(lambda: [('', header)]), height=1),
                Window(FormattedTextControl(rows)),
            ]
        )
    )
    Application(
        layout=layout,
        key_bindings=keys,
        full_screen=False,
        erase_when_done=True,
    ).run()

    if state['cancelled']:
        return []
    return list(checked.values())


def select_named(roles, specs):
    """Matches ACCOUNT_ID/ROLE_NAME against the listRoles result."""
    by_key = {(r['account_id'], r['role_name']): r for r in roles}
    selected, unknown = [], []
    for spec in specs:
        account, sep, name = spec.partition('/')
        key = (account.strip(), name.strip())
        if not sep or not all(key):
            unknown.append((spec, 'expected ACCOUNT_ID/ROLE_NAME'))
        elif key not in by_key:
            unknown.append((spec, 'no access'))
        elif by_key[key] not in selected:
            selected.append(by_key[key])
    return selected, unknown


def dpop_pem():
    """Same P-256 key and PEM shape aws login writes today."""
    key = EC.new_generate(ECType.P_256)
    body = textwrap.fill(
        base64.b64encode(key.export_key(ECExportFormat.SEC1)).decode('utf-8'),
        width=64,
    )
    return (
        f'-----BEGIN EC PRIVATE KEY-----\n{body}\n'
        '-----END EC PRIVATE KEY-----\n'
    )


def cache_dir():
    return os.path.expanduser(
        os.environ.get('AWS_LOGIN_CACHE_DIRECTORY')
        or os.path.join('~', '.aws', 'login', 'cache')
    )


def config_path():
    return os.path.expanduser(
        os.environ.get('AWS_CONFIG_FILE')
        or os.path.join('~', '.aws', 'config')
    )


def profile_name(role):
    return '{}-{}'.format(role['role_name'], role['account_id'])


def write_profile(writer, role, session):
    writer.update_config(
        {
            '__section__': f'profile {profile_name(role)}',
            'login_session': session,
            'login_account_id': role['account_id'],
            'login_role_name': role['role_name'],
            'login_account_name': role['account_name'],
            'region': 'us-east-1',
        },
        config_path(),
    )


def write_cache_record(role, session, result):
    credentials = result.get('accessToken') or {}
    expires_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(seconds=int(result.get('expiresIn', 900)))
    ).strftime('%Y-%m-%dT%H:%M:%SZ')

    record = {
        'accessToken': {
            'accessKeyId': credentials.get('accessKeyId', ''),
            'secretAccessKey': credentials.get('secretAccessKey', ''),
            'sessionToken': credentials.get('sessionToken', ''),
            'accountId': role['account_id'],
            'expiresAt': expires_at,
        },
        'tokenType': result.get('tokenType', ''),
        'refreshToken': result.get('refreshToken', ''),
        'clientId': CLIENT_ID,
        'dpopKey': dpop_pem(),
    }

    directory = cache_dir()
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(
        directory,
        hashlib.sha256(session.encode('utf-8')).hexdigest() + '.json',
    )
    with open(path, 'w') as handle:
        json.dump(record, handle, indent=2)
    os.chmod(path, 0o600)


class MultiRoleLoginCommand(BasicCommand):
    NAME = 'multirole-login'
    DESCRIPTION = (
        'Signs in through the browser, lists the roles available, and '
        'configures a profile for each role selected. Runs against the '
        'Sign-In stub APIs.'
    )
    ARG_TABLE = [
        {
            'name': 'stub-url',
            'required': True,
            'help_text': 'Base URL of the Sign-In stub APIs.',
        },
        {
            'name': 'search',
            'default': '',
            'help_text': (
                'Sent to listRoles as the keyword parameter, and used as the '
                'starting filter in the picker.'
            ),
        },
        {
            'name': 'roles',
            'nargs': '+',
            'default': [],
            'help_text': (
                'Configure these roles and skip the picker, given as '
                'ACCOUNT_ID/ROLE_NAME.'
            ),
        },
    ]

    def _run_main(self, parsed_args, parsed_globals):
        real_config = os.path.expanduser(os.path.join('~', '.aws', 'config'))
        if os.path.abspath(config_path()) == os.path.abspath(real_config):
            uni_print(
                'Refusing to write to ~/.aws/config. Set AWS_CONFIG_FILE and '
                'AWS_LOGIN_CACHE_DIRECTORY to a scratch location first.\n',
                sys.stderr,
            )
            return 1

        client = StubClient(parsed_args.stub_url)
        try:
            token = sign_in(client)
            roles = client.list_roles(token, parsed_args.search)
        except StubError as error:
            uni_print(f'{error}\n', sys.stderr)
            return 1

        if not roles:
            uni_print('No roles available.\n')
            return 0

        accounts = len({r['account_id'] for r in roles})
        uni_print(
            f'{len(roles)} roles available across {accounts} account(s).\n\n'
        )

        missing = []
        if parsed_args.roles:
            selected, missing = select_named(roles, parsed_args.roles)
            for spec, reason in missing:
                uni_print(f'{spec}: {reason}\n', sys.stderr)
        else:
            try:
                selected = pick_roles(roles, parsed_args.search)
            except StubError as error:
                uni_print(f'{error}\n', sys.stderr)
                return 1
        if not selected:
            uni_print('Nothing selected.\n')
            return 1 if missing else 0

        writer = ConfigFileWriter()
        failures = 0
        for role in selected:
            try:
                result = client.exchange_role(token, role['role_arn'])
            except StubError as error:
                uni_print(f'failed:     {profile_name(role)}  {error}\n')
                failures += 1
                continue
            # No idToken comes back from token_exchange, so the role ARN
            # stands in as the per-role session identifier.
            session = role['role_arn']
            write_profile(writer, role, session)
            write_cache_record(role, session, result)
            uni_print(f'configured: {profile_name(role)}\n')

        written = len(selected) - failures
        plural = '' if written == 1 else 's'
        uni_print(f'\nWrote {written} profile{plural} to {config_path()}\n')
        if failures:
            uni_print(f'{failures} failed.\n')
        uni_print(
            '\nTry one with:\n  aws sts get-caller-identity --profile '
            f'{profile_name(selected[0])}\n\n'
        )
        return 1 if failures or missing else 0


def register_multirole_login(cli):
    cli.register(
        'building-command-table.main', MultiRoleLoginCommand.add_command
    )
