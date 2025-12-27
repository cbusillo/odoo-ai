const path = require('path');

module.exports = {
    resolve: {
        alias: {
            '@product_connect': path.resolve(__dirname, 'static/src'),
        },
        extensions: ['.js'],
    },
};
