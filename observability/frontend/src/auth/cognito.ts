import { UserManager, WebStorageStateStore, type User } from 'oidc-client-ts'
import { environment } from '../config/environment'

const userManager = new UserManager({
  authority: environment.cognitoIssuer,
  client_id: environment.cognitoClientId,
  redirect_uri: environment.redirectUri,
  post_logout_redirect_uri: environment.logoutUri,
  response_type: 'code',
  scope: 'openid email profile',
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  revokeTokensOnSignout: true,
  revokeTokenTypes: ['access_token', 'refresh_token'],
})

export const signIn = (): Promise<void> => userManager.signinRedirect()

export const completeSignIn = (): Promise<User> => userManager.signinRedirectCallback()

export const signOut = (): Promise<void> => userManager.signoutRedirect()

export const getCurrentUser = (): Promise<User | null> => userManager.getUser()
