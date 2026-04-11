// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/**
 * @title SecureMedicalRecords
 * @dev Mock implementation of the Blockchain Security Layer for Phase 2/3.
 * Manages identity, ownership, and document integrity via SHA-256 hashes.
 */
contract SecureMedicalRecords {
    
    struct Document {
        bytes32 documentHash;
        address owner;
        string ipfsUri;
        uint256 timestamp;
        bool isValid;
    }
    
    struct AccessLog {
        address accessor;
        uint256 timestamp;
        string action;
    }

    // Mapping from document ID to its structured metadata
    mapping(string => Document) public documents;
    
    // Mapping from document ID to its address-based permissions
    mapping(string => mapping(address => bool)) public hasAccess;
    
    // Mapping from document ID to its audit logs
    mapping(string => AccessLog[]) private auditTrail;

    event DocumentRegistered(string docId, bytes32 indexed hash, address indexed owner);
    event AccessGranted(string docId, address indexed doctor, address indexed patient);
    event AccessRevoked(string docId, address indexed doctor, address indexed patient);
    event DocumentAccessed(string docId, address indexed accessor, string action);

    modifier onlyOwner(string memory docId) {
        require(documents[docId].owner == msg.sender, "Caller is not the document owner");
        _;
    }

    modifier canCompute(string memory docId) {
        require(
            documents[docId].owner == msg.sender || hasAccess[docId][msg.sender],
            "No permission to access this document"
        );
        _;
    }

    /**
     * @dev Registers the SHA-256 hash of a medical document to the blockchain.
     */
    function registerDocument(string memory docId, bytes32 hash, string memory ipfsUri) public {
        require(!documents[docId].isValid, "Document already exists");
        
        documents[docId] = Document({
            documentHash: hash,
            owner: msg.sender,
            ipfsUri: ipfsUri,
            timestamp: block.timestamp,
            isValid: true
        });
        
        emit DocumentRegistered(docId, hash, msg.sender);
    }

    /**
     * @dev Temporarily grant read access for a physician/institution address.
     */
    function grantAccess(string memory docId, address doctor) public onlyOwner(docId) {
        hasAccess[docId][doctor] = true;
        emit AccessGranted(docId, doctor, msg.sender);
    }

    /**
     * @dev Revokes previously granted access for an entity.
     */
    function revokeAccess(string memory docId, address doctor) public onlyOwner(docId) {
        hasAccess[docId][doctor] = false;
        emit AccessRevoked(docId, doctor, msg.sender);
    }

    /**
     * @dev Verifies integrity and logs the access context immutably.
     */
    function verifyDocument(string memory docId) public canCompute(docId) returns (bytes32, string memory) {
        logAccess(docId, msg.sender, "VERIFIED");
        
        Document memory doc = documents[docId];
        return (doc.documentHash, doc.ipfsUri);
    }

    /**
     * @dev Internal log handler for the Audit Trail.
     */
    function logAccess(string memory docId, address accessor, string memory action) internal {
        auditTrail[docId].push(AccessLog({
            accessor: accessor,
            timestamp: block.timestamp,
            action: action
        }));
        emit DocumentAccessed(docId, accessor, action);
    }
}
