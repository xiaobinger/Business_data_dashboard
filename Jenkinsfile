pipeline {
    agent any

    environment {
        REPO_URL = 'https://github.com/xiaobinger/Business_data_dashboard.git'
        BRANCH   = 'main'
        DEPLOY_HOST = '192.168.10.172'
        DEPLOY_USER = 'root'
        DEPLOY_DIR  = '/opt/data_dashboard'
    }

    stages {
        stage('Checkout') {
            steps {
                git branch: "${BRANCH}", url: "${REPO_URL}"
            }
        }

        stage('Package') {
            steps {
                sh '''
                    tar czf data_dashboard.tar.gz \
                        --exclude='.git' \
                        --exclude='__pycache__' \
                        --exclude='data' \
                        --exclude='.env' \
                        --exclude='venv' \
                        --exclude='logs' \
                        .
                '''
            }
        }

        stage('Deploy') {
            steps {
                sh """
                    ssh ${DEPLOY_USER}@${DEPLOY_HOST} "mkdir -p ${DEPLOY_DIR} ${DEPLOY_DIR}/data ${DEPLOY_DIR}/logs"
                    scp data_dashboard.tar.gz ${DEPLOY_USER}@${DEPLOY_HOST}:${DEPLOY_DIR}/
                    ssh ${DEPLOY_USER}@${DEPLOY_HOST} """
                        cd ${DEPLOY_DIR} && \
                        tar xzf data_dashboard.tar.gz && \
                        rm -f data_dashboard.tar.gz && \
                        chmod +x deploy.sh && \
                        bash deploy.sh restart
                    """
            }
        }
    }

    post {
        success {
            echo 'Deploy succeeded!'
        }
        failure {
            echo 'Deploy failed! Check logs above.'
        }
        always {
            cleanWs()
        }
    }
}
