# Swissquote Track

## Swissquote Wallet Challenge

### Prize Pool

| Rank | Prize |
|------|-------|
| 1st | $1,800 USD |
| 2nd | $1,100 USD |
| 3rd | $700 USD |

## Objective

Build a secure self-custody cryptocurrency wallet that Swissquote
could realistically offer to its banking clients.

The wallet should allow users to control their own assets and
private keys while maintaining the security, simplicity,
compliance, and user experience expected from a Swiss bank.

**Core principle: Their keys, their control.**

Users should remain one step away from their Swissquote account
without giving Swissquote unintended control over their funds.

## Core Requirements

### 1. Wallet Creation
- Create a self-custody wallet.
- Define the custody model.
- Explain where private keys or key shares are stored.
- Securely initialize the wallet.

### 2. Authentication
- Implement secure user authentication.
- Protect access to wallet operations.
- Authenticate users before transaction signing.

### 3. Transaction Signing
- Sign transactions securely.
- Submit a real transaction to a blockchain.
- Testnet transactions are accepted.
- Demonstrate the complete signing flow.

### 4. Recovery
- Implement a loss-of-access recovery mechanism.
- Prevent unauthorized recovery attempts.
- Protect against compromised devices or email accounts.
- Avoid giving Swissquote unintended control over user assets.

### 5. Security Architecture
- Define a credible threat model.
- Explain the custody architecture.
- Document where keys and key shares live.
- Identify attack vectors and mitigations.
- Use established cryptographic libraries and SDKs.

### 6. Legal and Business Feasibility
- Address Swiss regulatory considerations.
- Consider wallet ownership verification.
- Explain how the product integrates into Swissquote.
- Present a realistic business case.

## Possible Technologies

### Wallet and Cryptography
- MPC / threshold signatures
- Passkeys and WebAuthn
- Smart contract accounts (ERC-4337)
- Seed phrases
- Shamir Secret Sharing
- SLIP-39 split backups

### Blockchain
- EVM-compatible networks
- Testnet deployment
- Smart contracts
- Transaction signing and broadcasting

IMPORTANT:
Use established cryptographic libraries.
Do not implement custom cryptographic primitives.

## Bonus Features

### Gasless Transactions
- Allow users to transfer tokens without holding native gas tokens.
- Example: USDC transfers without ETH.
- Potential approach: account abstraction and paymasters.

### Compliant dApp Interaction
- Approved dApp allowlists
- Sanctions screening
- Transaction simulation
- Additional verification for high-value transactions

### Advanced Recovery
- Distinguish legitimate users from attackers.
- Resist phone and email compromise.
- Provide a secure and practical recovery experience.

### Business Value
- Client retention
- New user acquisition
- Revenue opportunities
- Reduced operational costs
- Improved integration with Swissquote services

## Mocking Policy

Components that cannot realistically be implemented during
the hackathon may be mocked.

Examples:
- Banking infrastructure
- Compliance providers
- Key-share servers

All mocked components must be clearly documented and
their production architecture must remain credible.

## Judging Criteria

| Category | Points |
|----------|--------|
| Technical implementation | 35 |
| Security and custody design | 20 |
| Legal feasibility | 15 |
| Business case | 15 |
| User experience and pitch | 15 |
| Total base score | 100 |

Up to 20 additional bonus points are available for
well-executed gasless transactions and compliant dApp
interaction, provided the core wallet lifecycle works.

## Minimum Working Demo

The prototype must demonstrate:

1. CREATE a wallet
2. AUTHENTICATE the user
3. SIGN and SEND a real blockchain transaction
4. RECOVER access to the wallet

## Key Success Factors

- End-to-end wallet lifecycle
- Real blockchain transaction
- Strong self-custody guarantees
- Credible security and threat model
- Secure recovery mechanism
- Regulatory feasibility
- Excellent user experience
- Strong Swissquote business case

## Project Status

- Track selection: Pending
- Custody model: TBD
- Blockchain: TBD
- Technology stack: TBD
- MVP scope: TBD
- Team responsibilities: TBD
